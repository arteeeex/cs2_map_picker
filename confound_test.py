"""O efeito 'solo e melhor' e real ou e so 'eu era mais novo / rank mais baixo'?"""
import json, os, sys, random
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import _parse_dt

CFG = json.load(open("config.json", encoding="utf-8")); ME = CFG["me"]
conn = store.connect(); ALL = store.load_matches(conn, ME); conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))
SZ = lambda m: len({str(p) for p in m["roster"]} - {ME})
W  = lambda m: 1 if m["result"]=="W" else 0

print("distribuicao de 'solo' ao longo do tempo (quartis do historico):")
q = len(ALL)//4
for i in range(4):
    blk = ALL[i*q:(i+1)*q] if i<3 else ALL[3*q:]
    solo = [m for m in blk if SZ(m)==0]
    d0=_parse_dt(blk[0]["played_at"]).strftime("%Y-%m"); d1=_parse_dt(blk[-1]["played_at"]).strftime("%Y-%m")
    ws=sum(W(m) for m in solo); wb=sum(W(m) for m in blk)
    print(f"  Q{i+1} {d0}..{d1}: {len(blk):>3} partidas | solo {len(solo):>2}"
          f" ({ws}V-{len(solo)-ws}D) | bloco {wb/len(blk)*100:.1f}%")

print("\nefeito do tamanho do grupo DENTRO de cada quartil:")
for i in range(4):
    blk = ALL[i*q:(i+1)*q] if i<3 else ALL[3*q:]
    by=defaultdict(list)
    for m in blk: by[min(SZ(m),2)].append(W(m))
    parts=[f"{k}:{sum(v)}/{len(v)}={sum(v)/len(v)*100:.0f}%" for k,v in sorted(by.items()) if len(v)>=8]
    print(f"  Q{i+1}: " + "  ".join(parts))

print("\nteste de tendencia SO no ultimo ano (remove o confundidor de epoca):")
import math
now = _parse_dt(ALL[-1]["played_at"])
rec = [m for m in ALL if (now - _parse_dt(m["played_at"])).days <= 365]
xs=[SZ(m) for m in rec]; ys=[W(m) for m in rec]
mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
obs=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
rng=random.Random(9); hits=0
for _ in range(50000):
    sh=ys[:]; rng.shuffle(sh)
    if abs(sum((x-mx)*(v-my) for x,v in zip(xs,sh))) >= abs(obs): hits+=1
print(f"  {len(rec)} partidas no ultimo ano | p = {hits/50000:.4f}")
by=defaultdict(list)
for m in rec: by[SZ(m)].append(W(m))
for k,v in sorted(by.items()):
    print(f"    {k} colegas: {sum(v)}/{len(v)} = {sum(v)/len(v)*100:.1f}%")
