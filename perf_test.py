"""O matchmaking equaliza o RESULTADO. Mas equaliza o seu RENDIMENTO?"""
import json, os, sys, random, math
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import _parse_dt

CFG = json.load(open("config.json", encoding="utf-8"))
ME = CFG["me"]
conn = store.connect(); ALL = store.load_matches(conn, ME); conn.close()
SZ = lambda m: len({str(p) for p in m["roster"]} - {ME})
CORE = [m for m in ALL if SZ(m) >= 1]

def test(metric, label, data):
    vals = defaultdict(list)
    for m in data:
        ps = m["players"].get(ME)
        if not ps: continue
        v = metric(m, ps)
        if v is not None: vals[m["map"]].append(v)
    vals = {k: v for k, v in vals.items() if len(v) >= 8}
    allv = [x for v in vals.values() for x in v]
    gm = sum(allv)/len(allv)
    # F de uma ANOVA, com p por permutacao
    def F(groups):
        k = len(groups); n = sum(len(g) for g in groups)
        gmu = sum(x for g in groups for x in g)/n
        ssb = sum(len(g)*(sum(g)/len(g)-gmu)**2 for g in groups)
        ssw = sum((x-sum(g)/len(g))**2 for g in groups for x in g)
        return (ssb/(k-1))/(ssw/(n-k)) if ssw > 1e-9 else 0
    groups = list(vals.values()); obs = F(groups)
    sizes = [len(g) for g in groups]; rng = random.Random(3); hits = 0
    for _ in range(20000):
        sh = allv[:]; rng.shuffle(sh)
        gs, i = [], 0
        for s in sizes: gs.append(sh[i:i+s]); i += s
        if F(gs) >= obs: hits += 1
    p = hits/20000
    print(f"\n  {label}  (media geral {gm:.2f})")
    for mp, v in sorted(vals.items(), key=lambda kv: -sum(kv[1])/len(kv[1])):
        mu = sum(v)/len(v)
        print(f"    {mp:<13} {mu:>6.2f}  n={len(v):<3} {'+' if mu>=gm else ''}{mu-gm:+.2f}")
    print(f"    F={obs:.2f}  p={p:.4f}  -> {'DIFERENCA REAL' if p<0.05 else 'compativel com acaso'}")
    return p

print("="*60); print("RENDIMENTO INDIVIDUAL POR MAPA (so partidas com colega)"); print("="*60)
test(lambda m,p: p["rating"], "Rating", CORE)
test(lambda m,p: p["adr"], "ADR", CORE)
test(lambda m,p: p["kills"]/max(p["deaths"],1), "K/D", CORE)
