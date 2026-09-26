#!/usr/bin/env python3
"""mappick - qual mapa pickar, calculado do seu historico.

  python mappick.py web                  abre a pagina local (interface principal)
  python mappick.py seed                 popula com dados de exemplo para testar
  python mappick.py rank [nome|steam64]  ranking no terminal, com o lobby dado
  python mappick.py sync                 baixa partidas novas da fonte configurada
  python mappick.py import ARQUIVO       importa CSV/JSON de partidas
  python mappick.py players              lista os colegas conhecidos
  python mappick.py friend NOME [off]    fixa alguem como time fixo
  python mappick.py setme STEAM64        define quem e voce
  python mappick.py dedupe               remove partidas repetidas entre fontes
  python mappick.py csstats-js  IDs      gera o coletor p/ colar no console
  python mappick.py csstats-build        monta as partidas da coleta salva
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from mappick import store  # noqa: E402
from mappick.model import MapPicker  # noqa: E402

CONFIG = os.path.join(ROOT, "config.json")


def cfg_load():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def cfg_save(c):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=2, ensure_ascii=False)


def resolve(conn, token, me):
    """Aceita steam64 ou apelido."""
    token = str(token)
    if token.isdigit() and len(token) >= 16:
        return token
    row = conn.execute(
        "SELECT steam64 FROM players WHERE lower(name)=lower(?) AND steam64<>?",
        (token, str(me))).fetchone()
    if row:
        return str(row["steam64"])
    raise SystemExit(f"nao achei jogador '{token}' - use `python mappick.py players`")


def cmd_seed(_args):
    from mappick.sources import synth
    conn = store.connect()
    me = synth.seed_db(conn, n_matches=400, seed=7)
    c = cfg_load()
    c["me"] = me
    cfg_save(c)
    n = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
    conn.close()
    print(f"ok: {n} partidas de exemplo, 'me' = {me}")
    print("agora rode:  python mappick.py web")


def cmd_web(args):
    from mappick.server import serve
    port = int(args[0]) if args else 8770
    serve(port=port)


def cmd_players(_args):
    c = cfg_load()
    conn = store.connect()
    rows = store.known_players(conn, c.get("me"))
    conn.close()
    if not rows:
        return print("nenhum colega no banco ainda.")
    print(f"{'steam64':<20} {'nome':<16} {'jogos':>6}")
    for r in rows:
        print(f"{r['steam64']:<20} {(r['name'] or '-'):<16} {r['games']:>6}")


def cmd_setme(args):
    if not args:
        raise SystemExit("uso: python mappick.py setme STEAM64")
    c = cfg_load()
    c["me"] = str(args[0])
    for s in c.get("sources", {}).values():
        if not s.get("steam64"):
            s["steam64"] = str(args[0])
    cfg_save(c)
    print("me =", c["me"])


def cmd_rank(args):
    c = cfg_load()
    me = c.get("me")
    if not me:
        raise SystemExit("defina o seu steam64: python mappick.py setme STEAM64")
    conn = store.connect()
    mates = [resolve(conn, a, me) for a in args]
    matches = store.load_matches(conn, me)
    names = {str(p["steam64"]): p["name"] for p in store.known_players(conn, None)}
    conn.close()
    if not matches:
        raise SystemExit("sem partidas - rode `python mappick.py seed` ou `sync`")

    res = MapPicker(matches, me, c).rank(mates)
    lobby = ", ".join(names.get(p) or p[-5:] for p in res["lobby"])
    print(f"\n  lobby: {lobby}")
    print(f"  {res['total_matches']} partidas na janela | base geral "
          f"{res['global_baseline']*100:.1f}%\n")
    print(f"  {'#':>2} {'mapa':<12} {'vitoria':>8}  {'intervalo 90%':>15}  "
          f"{'n_ef':>5}  {'conf':<9} time exato")
    print("  " + "-" * 74)
    for m in res["maps"]:
        bar = "#" * round(m["p_win"] * 22)
        print(f"  {m['rank']:>2} {m['map'].replace('de_',''):<12} "
              f"{m['p_win']*100:>7.1f}%  "
              f"{m['p_low']*100:>6.1f}-{m['p_high']*100:<6.1f}%  "
              f"{m['n_eff']:>5.1f}  {m['confidence']:<9} "
              f"{m['exact_w']}V{m['exact_l']}D  {bar}")
    print()


def cmd_sync(_args):
    """Roda TODAS as fontes ligadas e depois deduplica.

    Nenhuma fonte sozinha tem o historico completo (o Leetify so anda para a
    frente a partir de quando a conta foi conectada), entao a estrategia e
    somar as fontes e remover a sobreposicao.
    """
    c = cfg_load()
    srcs = c.get("sources", {})
    total = 0
    conn = store.connect()
    try:
        if srcs.get("csstats", {}).get("enabled"):
            from mappick.sources import csstats
            sid = srcs["csstats"].get("steam64") or c.get("me")
            if sid:
                try:
                    total += csstats.sync(conn, sid, verbose=True)
                except SystemExit as e:
                    print(f"csstats: {e}")
            else:
                print("csstats: sem steam64 configurado, pulando")
        if srcs.get("leetify", {}).get("enabled"):
            from mappick.sources import leetify
            sid = srcs["leetify"].get("steam64") or c.get("me")
            if sid:
                try:
                    total += leetify.sync(conn, sid, verbose=True)
                except SystemExit as e:
                    print(f"leetify: {e}")
            else:
                print("leetify: sem steam64 configurado, pulando")
        conn.commit()
        store.backfill_dedupe_keys(conn)
        dup = store.dedupe(conn, verbose=True)
        n = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
    finally:
        conn.close()
    print(f"\nsync: +{total} partidas | {dup} duplicatas removidas | {n} no banco")


def cmd_csstats_js(args):
    """Imprime o coletor para colar no console do CSStats (F12)."""
    from mappick.sources import csstats
    c = cfg_load()
    ids = args or c.get("group") or ([c["me"]] if c.get("me") else [])
    if not ids:
        raise SystemExit("uso: python mappick.py csstats-js STEAM64 [STEAM64 ...]")
    port = int(c.get("port", 8770))
    print("\n1. suba o servidor noutro terminal:  python mappick.py web")
    print("2. abra https://csstats.gg no navegador e faca login")
    print("3. abra o console (F12) e cole isto:\n")
    print(csstats.bookmarklet(ids, port))


def cmd_csstats_build(_args):
    """Processa o payload cru ja coletado, agora que 'me' esta definido."""
    import json as _json
    from mappick.sources import csstats
    c = cfg_load()
    me = c.get("me")
    if not me:
        raise SystemExit("defina primeiro: python mappick.py setme STEAM64")
    path = os.path.join(ROOT, "data", "raw_csstats.json")
    if not os.path.exists(path):
        raise SystemExit("nao ha coleta salva - rode o csstats-js primeiro")
    with open(path, encoding="utf-8") as f:
        payload = _json.load(f)
    per = payload.get("per_player", {})
    if str(me) not in per:
        raise SystemExit(f"o seu steam64 ({me}) nao esta na coleta. "
                         f"coletados: {list(per)}")
    conn = store.connect()
    try:
        n = csstats.ingest(conn, per, me, payload.get("names") or {})
        store.backfill_dedupe_keys(conn)
        dup = store.dedupe(conn)
        total = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
    finally:
        conn.close()
    print(f"{n} partidas montadas | {dup} duplicatas | {total} no banco")


def cmd_dedupe(_args):
    conn = store.connect()
    try:
        store.backfill_dedupe_keys(conn)
        n = store.dedupe(conn, verbose=True)
    finally:
        conn.close()
    print(f"{n} duplicatas removidas")


def cmd_friend(args):
    """Fixa (ou solta) alguem como time fixo, para ficar sempre visivel na lista."""
    if not args:
        raise SystemExit("uso: python mappick.py friend NOME|STEAM64 [off]")
    off = len(args) > 1 and args[1].lower() in ("off", "0", "nao", "remove")
    c = cfg_load()
    conn = store.connect()
    try:
        sid = resolve(conn, args[0], c.get("me"))
        store.set_friend(conn, sid, not off)
        row = conn.execute("SELECT name FROM players WHERE steam64=?", (sid,)).fetchone()
    finally:
        conn.close()
    print(f"{row['name'] if row and row['name'] else sid}: "
          f"{'solto' if off else 'fixado como time'}")


def cmd_import(args):
    if not args:
        raise SystemExit("uso: python mappick.py import ARQUIVO.(csv|json)")
    from mappick.sources import manual
    conn = store.connect()
    try:
        n = manual.import_file(conn, args[0], cfg_load().get("me"))
        conn.commit()
    finally:
        conn.close()
    print(f"importadas {n} partidas de {args[0]}")


COMMANDS = {"web": cmd_web, "seed": cmd_seed, "rank": cmd_rank, "sync": cmd_sync,
            "import": cmd_import, "players": cmd_players, "setme": cmd_setme,
            "dedupe": cmd_dedupe, "friend": cmd_friend,
            "csstats-js": cmd_csstats_js, "csstats-build": cmd_csstats_build}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(f"comando desconhecido: {cmd}")
    COMMANDS[cmd](sys.argv[2:])
