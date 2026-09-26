"""Carrega o recorte real coletado do CSStats para dentro do banco.

Formato de data/real_recent.csv (uma linha por partida, do ponto de vista de me):
    match_id, unix_ts, map_idx, rw, rl, k, d, a, adr, hs, rating, roster

`roster` tem 4 posicoes, uma por colega, na ordem de GROUP[1:]:
    A = jogou do meu lado   E = jogou contra   - = nao estava na partida
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store  # noqa: E402

ME = "76561198816645847"
GROUP = [ME, "76561198426648959", "76561198799388505",
         "76561199039885619", "76561198344042074"]
NAMES = {
    "76561198816645847": "resenha ou morte",
    "76561198426648959": "KICK PRETTOWSKI",
    "76561198799388505": "pissa",
    "76561199039885619": "M&MNEM",
    "76561198344042074": "Rick",
}
MAPS = ["cs_italy", "cs_office", "de_ancient", "de_anubis", "de_basalt",
        "de_cache", "de_dust2", "de_inferno", "de_mirage", "de_nuke",
        "de_overpass", "de_train", "de_vertigo"]

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "real_recent.csv")
conn = store.connect()
n = 0
with open(path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        p = line.split(",")
        mid, ts, midx, rw, rl, k, d, a, adr, hs, rating, roster = p[:12]
        rw, rl = int(rw), int(rl)
        players = [{
            "steam64": ME, "name": NAMES[ME], "is_ally": True,
            "kills": int(k), "deaths": int(d), "assists": int(a),
            "adr": float(adr), "kast": None, "hs_pct": float(hs),
            "rating": float(rating) if rating else None,
        }]
        for i, flag in enumerate(roster):
            if flag == "-":
                continue
            sid = GROUP[i + 1]
            players.append({
                "steam64": sid, "name": NAMES[sid], "is_ally": flag == "A",
                "kills": None, "deaths": None, "assists": None,
                "adr": None, "kast": None, "hs_pct": None, "rating": None,
            })
        store.upsert_match(conn, {
            "id": f"cs_{mid}", "source": "csstats",
            "played_at": datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(),
            "map": MAPS[int(midx)], "mode": "premier",
            "rounds_won": rw, "rounds_lost": rl,
            "result": "W" if rw > rl else "L" if rl > rw else "D",
            "players": players, "raw": None,
        })
        n += 1

for sid, nm in NAMES.items():
    conn.execute(
        "INSERT INTO players (steam64,name,is_friend,updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(steam64) DO UPDATE SET name=excluded.name, is_friend=excluded.is_friend",
        (sid, nm, 0 if sid == ME else 1, datetime.now(timezone.utc).isoformat()))
conn.commit()
store.backfill_dedupe_keys(conn)
print(f"{n} partidas reais carregadas")
conn.close()
