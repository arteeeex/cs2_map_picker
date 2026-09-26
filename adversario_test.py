"""Ultima alavanca: controlar pela FORCA DO ADVERSARIO.

Ideia: o rank.change do Premier e ~ K*(resultado - expectativa). Ele nao serve
como preditor (so existe depois da partida), mas serve para corrigir o PESO da
evidencia passada: vencer um time muito mais forte diz mais sobre o mapa do que
vencer um fraco. Recuperando a expectativa, o alvo deixa de ser "ganhou?" e vira
"ganhou mais do que se esperava?", o que remove a variacao de adversario.
"""
import math, os
from collections import defaultdict

ROWS=[]
for part in ("full_01.csv","full_02.csv","full_03.csv"):
    for line in open(os.path.join("data",part), encoding="utf-8"):
        p=line.strip().split(",")
        if not p or not p[0]: continue
        rw,rl=int(p[2]),int(p[3]); k,d=int(p[4]),int(p[5])
        adr=float(p[7]); chg=int(p[11]) if p[11] else 0
        rnew=int(p[12]) if len(p)>12 and p[12] else 0
        if chg==-1000 or adr==0 or (k==0 and d<=1) or max(rw,rl)<13: continue
        if rnew<=0 or chg==0: continue          # so Premier com change valido
        ROWS.append(dict(ts=int(p[0]), map=int(p[1]), rw=rw, rl=rl,
                         y=1.0 if rw>rl else (0.0 if rl>rw else .5),
                         chg=chg, rank=rnew, roster=p[10]))
ROWS.sort(key=lambda r:r["ts"])
print(f"{len(ROWS)} partidas de Premier com rank change valido")

# estima K: change ~ K*(y - expectativa); num conjunto equilibrado E[exp]=.5,
# entao E[change | vitoria] ~ K/2 e E[change | derrota] ~ -K/2
vw=[r["chg"] for r in ROWS if r["y"]==1]; vl=[r["chg"] for r in ROWS if r["y"]==0]
K = (sum(vw)/len(vw) - sum(vl)/len(vl))
print(f"  change medio: vitoria {sum(vw)/len(vw):+.0f} | derrota {sum(vl)/len(vl):+.0f}  ->  K = {K:.0f}")

for r in ROWS:
    exp = r["y"] - r["chg"]/K
    r["exp"] = min(max(exp, 0.02), 0.98)
    r["surpresa"] = r["y"] - r["exp"]

print(f"\n  expectativa media do sistema: {sum(r['exp'] for r in ROWS)/len(ROWS):.3f}")
print(f"  (se o matchmaking fosse perfeitamente equilibrado, seria 0.50)")

print("\n== forca por mapa: bruto vs corrigido pela dificuldade ==")
print(f"  {'mapa':<8} {'n':>4} {'winrate':>8} {'dificuldade':>12} {'surpresa':>10}")
MAPS=["italy","office","ancient","anubis","basalt","cache","dust2","inferno",
      "mirage","nuke","overpass","train","vertigo"]
by=defaultdict(list)
for r in ROWS: by[r["map"]].append(r)
linhas=[]
for mi,rs in sorted(by.items(), key=lambda kv:-len(kv[1])):
    if len(rs)<40: continue
    wr=sum(r["y"] for r in rs)/len(rs)
    dif=sum(r["exp"] for r in rs)/len(rs)
    sur=sum(r["surpresa"] for r in rs)/len(rs)
    linhas.append((MAPS[mi],len(rs),wr,dif,sur))
for nome,n,wr,dif,sur in sorted(linhas,key=lambda x:-x[4]):
    print(f"  {nome:<8} {n:>4} {wr*100:>7.1f}% {dif*100:>11.1f}% {sur*100:>+9.1f} pp")

# o ranking muda ao corrigir?
a=[x[0] for x in sorted(linhas,key=lambda x:-x[2])]
b=[x[0] for x in sorted(linhas,key=lambda x:-x[4])]
print(f"\n  ordem por winrate bruto : {a}")
print(f"  ordem por surpresa      : {b}")
ra={m:i for i,m in enumerate(a)}; rb={m:i for i,m in enumerate(b)}
n=len(a); d2=sum((ra[m]-rb[m])**2 for m in a)
print(f"  Spearman entre as duas ordens: {1-6*d2/(n*(n*n-1)):+.3f}")

# ---------------------------------------------------------------------------
print("\n" + "="*66)
print("O SINAL FICA MAIS FORTE AO CORRIGIR PELA DIFICULDADE?")
print("="*66)
import random
rng=random.Random(17)

def perm_test(valor, label):
    grupos=[[valor(r) for r in rs] for mi,rs in by.items() if len(rs)>=40]
    todos=[x for g in grupos for x in g]; sizes=[len(g) for g in grupos]
    def F(gs):
        n=sum(len(g) for g in gs); gm=sum(x for g in gs for x in g)/n
        ssb=sum(len(g)*(sum(g)/len(g)-gm)**2 for g in gs)
        ssw=sum((x-sum(g)/len(g))**2 for g in gs for x in g)
        return (ssb/(len(gs)-1))/(ssw/(n-len(gs))) if ssw>1e-9 else 0
    obs=F(grupos); hits=0; N=20000
    for _ in range(N):
        sh=todos[:]; rng.shuffle(sh)
        gs=[]; i=0
        for s in sizes: gs.append(sh[i:i+s]); i+=s
        if F(gs)>=obs: hits+=1
    p=hits/N
    print(f"  {label:<34} F={obs:5.2f}  p={p:.4f}  {'** SINAL **' if p<0.05 else ''}")
    return p

p1=perm_test(lambda r: r["y"], "resultado bruto (ganhou/perdeu)")
p2=perm_test(lambda r: r["surpresa"], "surpresa (corrigido p/ adversario)")
p3=perm_test(lambda r: r["rw"]/(r["rw"]+r["rl"]), "round share bruto")
print(f"\n  corrigir pela dificuldade mudou o p de {p1:.4f} para {p2:.4f}")
