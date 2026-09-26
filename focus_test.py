"""Teste focado: so Premier, so mapas do pool com amostra util."""
import json, os, sys, math, random
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import _parse_dt

CFG = json.load(open("config.json", encoding="utf-8")); ME = CFG["me"]
conn = store.connect(); ALL = store.load_matches(conn, ME); conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))

def chi_and_p(data, label, min_n=40, rounds=False):
    by = defaultdict(lambda: [0,0,0])
    for m in data:
        b = by[m["map"]]
        b[0] += m["rounds_won"] if rounds else (1 if m["result"]=="W" else 0)
        b[1] += m["rounds_lost"] if rounds else (1 if m["result"]=="L" else 0)
        b[2] += 1
    by = {k:v for k,v in by.items() if v[2] >= min_n}
    if len(by) < 2: return
    tw = sum(v[0] for v in by.values()); tl = sum(v[1] for v in by.values())
    base = tw/(tw+tl)
    chi = 0.0; sizes = []
    print(f"\n  {label}  (base {base*100:.2f}%)")
    for mp,(w,l,k) in sorted(by.items(), key=lambda kv:-kv[1][0]/(kv[1][0]+kv[1][1])):
        r = w+l; e = r*base
        chi += (w-e)**2/e + (l-(r-e))**2/(r-e)
        sizes.append(r)
        print(f"    {mp:<13} n={k:<4} {w/r*100:>6.2f}%  ({w}-{l})")
    pool = [1]*tw + [0]*tl
    rng = random.Random(5); hits = 0; N = 20000
    for _ in range(N):
        rng.shuffle(pool); c = 0.0; i = 0
        for r in sizes:
            w = sum(pool[i:i+r]); i += r; e = r*base
            c += (w-e)**2/e + ((r-w)-(r-e))**2/(r-e)
        if c >= chi: hits += 1
    p = hits/N
    print(f"    chi2={chi:.2f}  p={p:.4f}  -> {'SINAL' if p<0.05 else 'acaso'}")

PREM = [m for m in ALL if (m.get("mode") or "") == "premier"]
print(f"760 partidas | {len(PREM)} Premier")
chi_and_p(ALL,  "TODAS, mapas com n>=40, por VITORIA")
chi_and_p(PREM, "SO PREMIER, n>=40, por VITORIA")
chi_and_p(PREM, "SO PREMIER, n>=40, por ROUNDS", rounds=True)
