"""Comparacao justa: MESMO conjunto de avaliacao, muda so o treino."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import MapPicker, _parse_dt, logit, sigmoid

CFG = json.load(open("config.json", encoding="utf-8")); ME = CFG["me"]
conn = store.connect(); ALL = store.load_matches(conn, ME); conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))
SZ = lambda m: len({str(p) for p in m["roster"]} - {ME})
Y  = lambda m: 1.0 if m["result"]=="W" else (0.0 if m["result"]=="L" else 0.5)

# conjunto de AVALIACAO fixo: so partidas com colega, da 81a em diante
evaluable = [m for m in ALL if SZ(m) >= 1]
TEST = evaluable[80:]
print(f"conjunto de avaliacao fixo: {len(TEST)} partidas (identico nos dois casos)\n")

def run(drop_anom):
    b, hit = [], []
    for cur in TEST:
        t = _parse_dt(cur["played_at"])
        hist = [m for m in ALL if _parse_dt(m["played_at"]) < t]
        if drop_anom:
            hist = [m for m in hist if SZ(m) >= 1]
        pk = MapPicker(hist, ME, CFG); pk.now = t
        pk.matches = pk._prepare(hist); pk._player_baselines = {}
        mates = {str(p) for p in cur["roster"]} - {ME}
        tg,_ = pk._level_global(); tm,_ = pk._level_map(cur["map"], tg)
        tr,_,_ = pk._level_roster(cur["map"], mates, tm)
        z,_ = pk._form_z(ME, cur["map"])
        p = min(max(sigmoid(logit(tr) + CFG["model"]["form_beta"]*z),1e-6),1-1e-6)
        b.append((p-Y(cur))**2); hit.append(1.0 if (p>=.5)==(Y(cur)>=.5) else 0.0)
    return sum(b)/len(b), sum(hit)/len(hit)

cb = sum((0.5-Y(m))**2 for m in TEST)/len(TEST)
b1,a1 = run(False)
b2,a2 = run(True)
print(f"  moeda 50%                          Brier {cb:.4f}")
print(f"  treino COM as 14 atipicas          Brier {b1:.4f}   acerto {a1*100:.1f}%")
print(f"  treino SEM as 14 atipicas (atual)  Brier {b2:.4f}   acerto {a2*100:.1f}%")
d = b1-b2
print(f"\n  filtrar as atipicas mudou o Brier em {-d:+.4f} "
      f"({'MELHOROU' if d>0 else 'piorou'})")
