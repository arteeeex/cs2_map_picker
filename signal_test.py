"""Existe sinal? Antes de afinar qualquer modelo, testar se ha o que prever.

Se as diferencas de winrate entre mapas forem compativeis com puro acaso, nao
existe modelo capaz de extrair ordem de pick confiavel - e isso precisa ser dito,
nao escondido atras de numeros bonitos.
"""
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import _parse_dt

CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "config.json"), encoding="utf-8"))
ME = CFG["me"]
conn = store.connect()
ALL = store.load_matches(conn, ME)
conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))
W = lambda m: 1 if m["result"] == "W" else 0

n, w = len(ALL), sum(W(m) for m in ALL)
base = w / n
print(f"{n} partidas | {w}V-{n-w}D | winrate geral {base*100:.1f}%\n")

# ---------------------------------------------------------------- por mapa
print("=" * 62)
print("1. AS DIFERENCAS ENTRE MAPAS SAO REAIS OU ACASO?")
print("=" * 62)
by_map = defaultdict(list)
for m in ALL:
    by_map[m["map"]].append(W(m))

print(f"  {'mapa':<13} {'n':>4} {'V':>4} {'winrate':>8} {'esperado±dp':>16}")
chi = 0.0
for mp, ws in sorted(by_map.items(), key=lambda kv: -len(kv[1])):
    k, v = len(ws), sum(ws)
    exp = k * base
    sd = math.sqrt(k * base * (1 - base))
    chi += (v - exp) ** 2 / (exp + 1e-9) + ((k - v) - (k - exp)) ** 2 / ((k - exp) + 1e-9)
    print(f"  {mp:<13} {k:>4} {v:>4} {v/k*100:>7.1f}% {exp:>8.1f}±{sd:<5.1f}")
df = len(by_map) - 1
# p-valor por simulacao: embaralha os resultados entre as partidas
obs = chi
hits = 0
rng = random.Random(42)
outcomes = [W(m) for m in ALL]
sizes = [len(v) for v in by_map.values()]
for _ in range(20000):
    sh = outcomes[:]
    rng.shuffle(sh)
    c, i = 0.0, 0
    for k in sizes:
        v = sum(sh[i:i + k]); i += k
        exp = k * base
        c += (v - exp) ** 2 / (exp + 1e-9) + ((k - v) - (k - exp)) ** 2 / ((k - exp) + 1e-9)
    if c >= obs:
        hits += 1
p = hits / 20000
print(f"\n  qui-quadrado = {chi:.2f} (gl={df})   p = {p:.4f}")
print("  -> " + ("as diferencas entre mapas NAO se distinguem do acaso"
                 if p > 0.05 else "ha diferenca real entre mapas"))

# -------------------------------------------------------------- por stack
print()
print("=" * 62)
print("2. JOGAR EM GRUPO MUDA ALGUMA COISA?")
print("=" * 62)
by_sz = defaultdict(list)
for m in ALL:
    by_sz[len({str(p) for p in m["roster"]} - {ME})].append(W(m))
print(f"  {'colegas':<9} {'n':>4} {'V':>4} {'winrate':>8}")
for sz in sorted(by_sz):
    ws = by_sz[sz]
    print(f"  {sz:<9} {len(ws):>4} {sum(ws):>4} {sum(ws)/len(ws)*100:>7.1f}%")

# ---------------------------------------------- estabilidade no tempo
print()
print("=" * 62)
print("3. O QUE FOI BOM NA 1a METADE CONTINUA BOM NA 2a?")
print("=" * 62)
half = len(ALL) // 2
a, b = ALL[:half], ALL[half:]
ra, rb = defaultdict(list), defaultdict(list)
for m in a: ra[m["map"]].append(W(m))
for m in b: rb[m["map"]].append(W(m))
comuns = [mp for mp in ra if mp in rb and len(ra[mp]) >= 5 and len(rb[mp]) >= 5]
print(f"  {'mapa':<13} {'1a metade':>12} {'2a metade':>12}")
xs, ys = [], []
for mp in sorted(comuns):
    x = sum(ra[mp]) / len(ra[mp]); y = sum(rb[mp]) / len(rb[mp])
    xs.append(x); ys.append(y)
    print(f"  {mp:<13} {x*100:>10.1f}% ({len(ra[mp]):>2}) {y*100:>8.1f}% ({len(rb[mp]):>2})")
if len(xs) > 2:
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
    r = num/den if den > 1e-9 else 0
    print(f"\n  correlacao entre as duas metades: r = {r:+.3f}")
    print("  -> " + ("mapa bom antes NAO prediz mapa bom depois"
                     if abs(r) < 0.4 else "ha persistencia real"))

# ------------------------------------------------- premier e equilibrio
print()
print("=" * 62)
print("4. POR QUE ~50%?")
print("=" * 62)
rounds_w = sum(m["rounds_won"] for m in ALL)
rounds_l = sum(m["rounds_lost"] for m in ALL)
close = sum(1 for m in ALL if abs(m["rounds_won"] - m["rounds_lost"]) <= 4)
print(f"  rounds ganhos/perdidos : {rounds_w}/{rounds_l} = {rounds_w/(rounds_w+rounds_l)*100:.1f}%")
print(f"  partidas decididas por <=4 rounds: {close}/{n} = {close/n*100:.0f}%")
print("  O Premier pareia por rating: o sistema busca justamente o equilibrio,")
print("  entao o winrate tende a ~50% em todo mapa, por construcao.")
