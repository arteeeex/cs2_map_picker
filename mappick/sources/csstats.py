"""Coletor CSStats.gg - fonte principal (Premier / Matchmaking da Valve).

Como o CSStats realmente entrega os dados
-----------------------------------------
O perfil (`/player/{id}`) nao traz as partidas: ele carrega por AJAX, e so
quando a aba esta em foco (`getStatsWhenVisible()`). A rota util e

    /player/{steam64}/stats

que devolve ~1 MB de HTML com um JSON embutido, `window.MATCH_DATA`, contendo
TODAS as partidas do jogador:

    {"date":1790036470,"id":508654924,"map":"de_mirage","score":[13,8],
     "result":"w","k":11,"d":14,"a":3,"hs":45,"adr":61,"rating":0.86,
     "rank":{"t":"premier","old":12737,"new":13090,"change":353}}

Ha tambem `/player/{steam64}/ajax/played-with` (JSON), com o agregado de com
quem voce jogou - util para descobrir o grupo, mas sem detalhe por partida.

Como o roster e reconstruido
----------------------------
O `MATCH_DATA` nao diz quem jogou com voce. Mas o `id` da partida e GLOBAL no
CSStats, entao basta baixar o MATCH_DATA de cada membro do grupo e cruzar:

  - mesmo `id` de partida  -> estavam na mesma partida;
  - mesmo `result`/`score` -> mesmo time (aliados);
  - `result` oposto        -> jogaram um contra o outro.

Assim o roster de centenas de partidas sai de N requisicoes (uma por pessoa),
sem precisar abrir partida por partida.

Cloudflare
----------
`/player/{id}/stats` esta atras do Cloudflare e recusa urllib/curl. Por isso a
coleta roda no NAVEGADOR (o script de `bookmarklet()`), que faz o fetch na
origem certa e entrega o JSON ao servidor local em /api/ingest. As funcoes de
parsing abaixo sao puras, entao rodam e sao testaveis sem rede.
"""
import json
import re
from datetime import datetime, timezone

from .. import store

MATCH_DATA_RE = re.compile(r"window\.MATCH_DATA\s*=\s*(\{.*?\});", re.S)


# ----------------------------------------------------------------- parsing
def parse_match_data(html):
    """Extrai a lista de partidas do HTML de /player/{id}/stats."""
    m = MATCH_DATA_RE.search(html)
    if not m:
        return []
    try:
        return json.loads(m.group(1)).get("rows", [])
    except json.JSONDecodeError:
        return []


def _score(row):
    sc = row.get("score") or []
    if len(sc) != 2:
        return None, None
    return int(sc[0]), int(sc[1])


def same_team(a, b):
    """Dois registros da MESMA partida sao do mesmo time?

    O score vem do ponto de vista de cada jogador, entao aliados veem [13,8] e
    adversarios veem [8,13]. O result confirma.
    """
    a1, a2 = _score(a)
    b1, b2 = _score(b)
    if None in (a1, a2, b1, b2):
        return (a.get("result") or "").lower() == (b.get("result") or "").lower()
    return (a1, a2) == (b1, b2)


def build_matches(per_player, me, names=None):
    """Junta o MATCH_DATA de varios jogadores em partidas com roster.

    per_player: {steam64: [rows...]}
    Devolve partidas normalizadas do ponto de vista de `me`.
    """
    me = str(me)
    names = names or {}
    if me not in per_player:
        raise ValueError(f"o steam64 {me} nao esta entre os perfis coletados")

    # indexa: match_id -> {steam64: row}
    index = {}
    for sid, rows in per_player.items():
        for row in rows or []:
            mid = row.get("id")
            if mid is None:
                continue
            index.setdefault(str(mid), {})[str(sid)] = row

    out = []
    for mid, players in index.items():
        mine = players.get(me)
        if mine is None:
            continue  # partida de outro membro do grupo em que eu nao joguei
        rw, rl = _score(mine)
        if rw is None:
            continue
        map_name = (mine.get("map") or "").lower()
        if not map_name:
            continue
        ts = mine.get("date")
        played = (datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                  if ts else None)
        if not played:
            continue

        entries = []
        for sid, row in players.items():
            hs = row.get("hs")
            entries.append({
                "steam64": sid,
                "name": names.get(sid),
                "is_ally": same_team(mine, row),
                "kills": row.get("k"), "deaths": row.get("d"), "assists": row.get("a"),
                "adr": row.get("adr"),
                "kast": None,  # CSStats nao expoe KAST aqui
                "hs_pct": float(hs) if hs is not None else None,
                "rating": row.get("rating"),
            })

        rank = mine.get("rank") or {}
        out.append({
            "id": f"cs_{mid}", "source": "csstats",
            "played_at": played, "map": map_name,
            "mode": rank.get("t"),
            "rounds_won": rw, "rounds_lost": rl,
            "result": "W" if rw > rl else "L" if rl > rw else "D",
            "players": entries, "raw": None,
        })
    out.sort(key=lambda m: m["played_at"], reverse=True)
    return out


def ingest(conn, per_player, me, names=None):
    """Grava no banco o payload coletado pelo navegador."""
    matches = build_matches(per_player, me, names)
    for m in matches:
        store.upsert_match(conn, m)
    conn.commit()
    return len(matches)


# ------------------------------------------------------------- bookmarklet
COLLECT_JS = r"""
/* mappick - coleta do CSStats. Cole no console de csstats.gg (F12). */
(async () => {
  const IDS = %IDS%;
  const PORT = %PORT%;
  const per = {}, names = {};
  for (const id of IDS) {
    try {
      const r = await fetch(`/player/${id}/stats`, {headers:{'X-Requested-With':'XMLHttpRequest'}});
      const t = await r.text();
      const m = t.match(/window\.MATCH_DATA\s*=\s*(\{[\s\S]*?\});/);
      per[id] = m ? JSON.parse(m[1]).rows : [];
      /* o apelido nao vem no fragmento /stats: esta na pagina do perfil */
      const p = await fetch(`/player/${id}`);
      const n = (await p.text()).match(/<title>Player statistics - ([^|]+)\|/);
      if (n) names[id] = n[1].trim().replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>');
      console.log(`mappick: ${names[id]||id} -> ${per[id].length} partidas`);
    } catch (e) { console.warn(`mappick: falhou ${id}`, e); per[id] = []; }
    await new Promise(r => setTimeout(r, 2500));   /* respeita o rate limit */
  }
  const res = await fetch(`http://127.0.0.1:${PORT}/api/ingest`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({per_player: per, names})
  });
  console.log('mappick:', await res.text());
})();
"""


def bookmarklet(ids, port=8770):
    return (COLLECT_JS
            .replace("%IDS%", json.dumps([str(i) for i in ids]))
            .replace("%PORT%", str(port)))
