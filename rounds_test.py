"""Vitoria/derrota descarta informacao. O saldo de rounds tem sinal por mapa?

264 partidas sao 264 amostras binarias, mas ~5.500 rounds. Se existe diferenca
real de forca entre mapas, ela aparece muito mais cedo no round share do que no
winrate. Este e o teste decisivo antes de dizer que nao ha nada a extrair.
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

SZ = lambda m: len({str(p) for p in m["roster"]} - {ME})
# exclui o grupo anomalo de partidas sem nenhum colega conhecido (13V-1D,
# placares esmagadores: nao parece o mesmo contexto competitivo)
CORE = [m for m in ALL if SZ(m) >= 1]
print(f"{len(ALL)} partidas | {len(CORE)} apos remover o grupo anomalo 'sem colega'\n")


def analyse(data, label):
    print("=" * 64)
    print(label)
    print("=" * 64)
    by = defaultdict(lambda: [0, 0, 0])   # rounds_pro, rounds_contra, n
    for m in data:
        b = by[m["map"]]
        b[0] += m["rounds_won"]; b[1] += m["rounds_lost"]; b[2] += 1
    tot_w = sum(v[0] for v in by.values())
    tot_l = sum(v[1] for v in by.values())
    base = tot_w / (tot_w + tot_l)
    print(f"  round share geral: {base*100:.2f}%  ({tot_w}-{tot_l})\n")
    print(f"  {'mapa':<13} {'n':>4} {'rounds':>10} {'share':>8} {'±dp esperado':>14}")
    chi = 0.0
    sizes = []
    for mp, (w, l, k) in sorted(by.items(), key=lambda kv: -kv[1][2]):
        r = w + l
        sizes.append((mp, r))
        exp = r * base
        sd = math.sqrt(r * base * (1 - base))
        chi += (w - exp) ** 2 / exp + (l - (r - exp)) ** 2 / (r - exp)
        print(f"  {mp:<13} {k:>4} {w:>4}-{l:<4} {w/r*100:>7.2f}% {exp:>8.1f}±{sd:<5.1f}")

    # permutacao: embaralha os rounds entre os mapas preservando os tamanhos
    pool = [1] * tot_w + [0] * tot_l
    rng = random.Random(11)
    hits = 0
    N = 10000
    for _ in range(N):
        rng.shuffle(pool)
        c, i = 0.0, 0
        for _mp, r in sizes:
            w = sum(pool[i:i + r]); i += r
            exp = r * base
            c += (w - exp) ** 2 / exp + ((r - w) - (r - exp)) ** 2 / (r - exp)
        if c >= chi:
            hits += 1
    p = hits / N
    print(f"\n  qui-quadrado (rounds) = {chi:.2f}   p = {p:.4f}")
    print("  -> " + ("SINAL REAL entre mapas no saldo de rounds" if p < 0.05
                     else "nem no saldo de rounds ha diferenca distinguivel de acaso"))
    return p


analyse(ALL, "1. TODAS AS PARTIDAS")
print()
analyse(CORE, "2. SO AS PARTIDAS COM PELO MENOS UM COLEGA CONHECIDO")

# --------------------------------------------------- previsao out-of-sample
print()
print("=" * 64)
print("3. PREVER O ROUND SHARE DA PROXIMA PARTIDA")
print("=" * 64)
WARMUP = 80
data = CORE
def mse(fn):
    e = []
    for i in range(WARMUP, len(data)):
        h, c = data[:i], data[i]
        y = c["rounds_won"] / (c["rounds_won"] + c["rounds_lost"])
        e.append((fn(h, c) - y) ** 2)
    return sum(e) / len(e)

def f_base(h, c):
    w = sum(m["rounds_won"] for m in h); l = sum(m["rounds_lost"] for m in h)
    return w / (w + l) if (w + l) else 0.5
def f_map(h, c):
    sel = [m for m in h if m["map"] == c["map"]]
    if len(sel) < 3: return f_base(h, c)
    w = sum(m["rounds_won"] for m in sel); l = sum(m["rounds_lost"] for m in sel)
    return w / (w + l)
def f_map_shrunk(h, c):
    sel = [m for m in h if m["map"] == c["map"]]
    base = f_base(h, c)
    if not sel: return base
    w = sum(m["rounds_won"] for m in sel); l = sum(m["rounds_lost"] for m in sel)
    n, k = len(sel), 15
    return (n * (w / (w + l)) + k * base) / (n + k)

print(f"  constante 0.5             {mse(lambda h,c: 0.5):.5f}")
print(f"  round share geral         {mse(f_base):.5f}")
print(f"  por mapa (cru)            {mse(f_map):.5f}")
print(f"  por mapa (encolhido)      {mse(f_map_shrunk):.5f}")
