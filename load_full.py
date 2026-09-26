"""Carrega as 792 partidas completas, com limpeza.

Formato: ts, mapIdx, rw, rl, k, d, a, adr, hs, rating, roster, rankChange, rankNew

Limpeza (cada regra saiu de olhar os dados, nao de teoria):
  - rankChange == -1000  -> punicao por abandono;
  - adr == 0 ou k == 0 com d <= 1 -> desconectou, nao jogou;
  - max(rw,rl) < 13 -> partida nao terminou (aparece como 8x0, 12x12, 1x0);
  - rankNew == 0/vazio -> nao e Premier (competitivo comum): fica, mas marcado,
    porque o pareamento e o veto sao diferentes.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store

ME = "76561198816645847"
MATES = ["76561198426648959", "76561198799388505",
         "76561199039885619", "76561198344042074"]
NAMES = {ME: "resenha ou morte", MATES[0]: "KICK PRETTOWSKI", MATES[1]: "pissa",
         MATES[2]: "M&MNEM", MATES[3]: "Rick"}
MAPS = ["cs_italy", "cs_office", "de_ancient", "de_anubis", "de_basalt",
        "de_cache", "de_dust2", "de_inferno", "de_mirage", "de_nuke",
        "de_overpass", "de_train", "de_vertigo"]

HERE = os.path.dirname(os.path.abspath(__file__))
rows, descartes = [], {"abandono": 0, "incompleta": 0, "sem_stats": 0}

for part in ("full_01.csv", "full_02.csv", "full_03.csv"):
    with open(os.path.join(HERE, "data", part), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = line.split(",")
            ts, midx, rw, rl = int(p[0]), int(p[1]), int(p[2]), int(p[3])
            k, d, a = int(p[4]), int(p[5]), int(p[6])
            adr, hs = float(p[7]), float(p[8])
            rating = float(p[9]) if p[9] else None
            roster = p[10]
            chg = int(p[11]) if len(p) > 11 and p[11] not in ("", None) else 0
            rnew = int(p[12]) if len(p) > 12 and p[12] not in ("", None) else 0

            if chg == -1000:
                descartes["abandono"] += 1; continue
            if adr == 0 or (k == 0 and d <= 1):
                descartes["sem_stats"] += 1; continue
            if max(rw, rl) < 13:
                descartes["incompleta"] += 1; continue

            rows.append(dict(ts=ts, midx=midx, rw=rw, rl=rl, k=k, d=d, a=a, adr=adr,
                             hs=hs, rating=rating, roster=roster, chg=chg, rnew=rnew))

print(f"792 lidas | descartes: {descartes} | ficaram {len(rows)}")
premier = sum(1 for r in rows if r["rnew"] > 0)
print(f"  Premier: {premier} | competitivo comum: {len(rows)-premier}")

db = os.path.join(HERE, "data", "matches.db")
if os.path.exists(db):
    os.remove(db)
conn = store.connect(db)
for r in rows:
    players = [{
        "steam64": ME, "name": NAMES[ME], "is_ally": True,
        "kills": r["k"], "deaths": r["d"], "assists": r["a"],
        "adr": r["adr"], "kast": None, "hs_pct": r["hs"], "rating": r["rating"],
    }]
    for i, flag in enumerate(r["roster"]):
        if flag == "-":
            continue
        sid = MATES[i]
        players.append({"steam64": sid, "name": NAMES[sid], "is_ally": flag == "A",
                        "kills": None, "deaths": None, "assists": None,
                        "adr": None, "kast": None, "hs_pct": None, "rating": None})
    store.upsert_match(conn, {
        "id": f"cs_{r['ts']}", "source": "csstats",
        "played_at": datetime.fromtimestamp(r["ts"], tz=timezone.utc).isoformat(),
        "map": MAPS[r["midx"]], "mode": "premier" if r["rnew"] > 0 else "competitive",
        "rounds_won": r["rw"], "rounds_lost": r["rl"],
        "result": "W" if r["rw"] > r["rl"] else "L" if r["rl"] > r["rw"] else "D",
        "players": players,
        "raw": {"rank_change": r["chg"], "rank_new": r["rnew"]},
    })
for sid, nm in NAMES.items():
    conn.execute("INSERT INTO players (steam64,name,is_friend,updated_at) VALUES (?,?,?,?) "
                 "ON CONFLICT(steam64) DO UPDATE SET name=excluded.name, is_friend=excluded.is_friend",
                 (sid, nm, 0 if sid == ME else 1, datetime.now(timezone.utc).isoformat()))
conn.commit()
store.backfill_dedupe_keys(conn)
n = conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]
w = conn.execute("SELECT COUNT(*) c FROM matches WHERE result='W'").fetchone()["c"]
print(f"gravadas {n} | {w}V-{n-w}D ({w/n*100:.1f}%)")
conn.close()
