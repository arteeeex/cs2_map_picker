"""O efeito do tamanho do grupo e real ou artefato?

Testes:
  a) tendencia monotonica (Cochran-Armitage por permutacao);
  b) as 14 partidas "solo" sao mesmo solo, ou um vies de coleta?
  c) o efeito sobrevive fora da amostra (backtest so com stack size)?
"""
import json
import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone

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
SZ = lambda m: len({str(p) for p in m["roster"]} - {ME})

print("=" * 64)
print("a) A TENDENCIA E SIGNIFICATIVA?")
print("=" * 64)
xs = [SZ(m) for m in ALL]
ys = [W(m) for m in ALL]
mx = sum(xs) / len(xs)
my = sum(ys) / len(ys)
obs = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
rng = random.Random(7)
hits = 0
for _ in range(50000):
    sh = ys[:]
    rng.shuffle(sh)
    t = sum((x - mx) * (v - my) for x, v in zip(xs, sh))
    if abs(t) >= abs(obs):
        hits += 1
p = hits / 50000
print(f"  covariancia observada = {obs:.2f}   p (bicaudal) = {p:.5f}")
print("  -> " + ("tendencia REAL: mais colegas, pior o resultado" if p < 0.05
                 else "compativel com acaso"))

# sem o grupo extremo de 14 partidas solo, o efeito continua?
sub = [(x, y) for x, y in zip(xs, ys) if x >= 1]
sx = [a for a, _ in sub]; sy = [b for _, b in sub]
mx2 = sum(sx)/len(sx); my2 = sum(sy)/len(sy)
obs2 = sum((a-mx2)*(b-my2) for a, b in sub)
hits = 0
for _ in range(50000):
    sh = sy[:]
    rng.shuffle(sh)
    t = sum((a-mx2)*(v-my2) for a, v in zip(sx, sh))
    if abs(t) >= abs(obs2):
        hits += 1
print(f"  sem o grupo solo (so 1..4 colegas): p = {hits/50000:.5f}")

print()
print("=" * 64)
print("b) AS 14 PARTIDAS 'SOLO' SAO CONFIAVEIS?")
print("=" * 64)
solo = [m for m in ALL if SZ(m) == 0]
print(f"  {'data':<12} {'mapa':<12} {'placar':>7}  res")
for m in solo:
    d = _parse_dt(m["played_at"]).strftime("%Y-%m-%d")
    print(f"  {d:<12} {m['map']:<12} {m['rounds_won']:>3}x{m['rounds_lost']:<3} {m['result']}")
span = (_parse_dt(solo[-1]["played_at"]) - _parse_dt(solo[0]["played_at"])).days
print(f"\n  {len(solo)} partidas espalhadas por {span} dias")
print("  ATENCAO: 'solo' aqui = nenhum dos 4 amigos conhecidos na partida.")
print("  Ele pode ter jogado com OUTRAS pessoas que nao estao na coleta,")
print("  entao este grupo nao e necessariamente 'jogando sozinho'.")

print()
print("=" * 64)
print("c) O EFEITO PREVE FORA DA AMOSTRA?")
print("=" * 64)
WARMUP = 80
def brier(fn):
    b = []
    for i in range(WARMUP, len(ALL)):
        hist, cur = ALL[:i], ALL[i]
        pr = min(max(fn(hist, cur), 0.02), 0.98)
        b.append((pr - W(cur)) ** 2)
    return sum(b) / len(b)

def f_const(h, c): return 0.5
def f_stack(h, c):
    sel = [m for m in h if SZ(m) == SZ(c)]
    return sum(W(m) for m in sel)/len(sel) if len(sel) >= 5 else 0.5
def f_stack_smooth(h, c):
    sel = [m for m in h if SZ(m) == SZ(c)]
    k = 12
    base = sum(W(m) for m in h)/len(h) if h else 0.5
    if not sel: return base
    return (len(sel)*(sum(W(m) for m in sel)/len(sel)) + k*base)/(len(sel)+k)

print(f"  moeda 50%                 {brier(f_const):.4f}")
print(f"  winrate por tamanho       {brier(f_stack):.4f}")
print(f"  idem, com encolhimento    {brier(f_stack_smooth):.4f}")
