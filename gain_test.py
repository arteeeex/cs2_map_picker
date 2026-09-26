"""Duas perguntas objetivas:

  1. As mudancas (filtrar as 14 atipicas) melhoraram a PREVISAO, ou so a honestidade?
  2. Analise de poder: com esta amostra, que tamanho de diferenca entre mapas
     seria possivel detectar? Se o minimo detectavel for enorme, o problema nao
     e o modelo - e que a pergunta nao cabe nos dados.
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import MapPicker, _parse_dt, logit, sigmoid

CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "config.json"), encoding="utf-8"))
ME = CFG["me"]
conn = store.connect()
ALL = store.load_matches(conn, ME)
conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))
SZ = lambda m: len({str(p) for p in m["roster"]} - {ME})
Y = lambda m: 1.0 if m["result"] == "W" else (0.0 if m["result"] == "L" else 0.5)
CORE = [m for m in ALL if SZ(m) >= 1]

WARMUP = 80


def backtest(data, cfg_model=None):
    cfg = {**CFG, "model": {**CFG["model"], **(cfg_model or {})}}
    b, hit = [], []
    for i in range(WARMUP, len(data)):
        hist, cur = data[:i], data[i]
        pk = MapPicker(hist, ME, cfg)
        pk.now = _parse_dt(cur["played_at"])
        pk.matches = pk._prepare(hist)
        pk._player_baselines = {}
        mates = {str(p) for p in cur["roster"]} - {ME}
        tg, _ = pk._level_global()
        tm, _ = pk._level_map(cur["map"], tg)
        tr, _, _ = pk._level_roster(cur["map"], mates, tm)
        z, _ = pk._form_z(ME, cur["map"])
        p = min(max(sigmoid(logit(tr) + cfg["model"]["form_beta"] * z), 1e-6), 1 - 1e-6)
        y = Y(cur)
        b.append((p - y) ** 2)
        hit.append(1.0 if (p >= .5) == (y >= .5) else 0.0)
    return sum(b) / len(b), sum(hit) / len(hit), len(b)


def const_brier(data):
    s = [(0.5 - Y(m)) ** 2 for m in data[WARMUP:]]
    return sum(s) / len(s)


print("=" * 68)
print("1. AS MUDANCAS MELHORARAM A PREVISAO?")
print("=" * 68)
for label, data in (("todas as 264", ALL), ("250, sem as atipicas", CORE)):
    br, ac, n = backtest(data)
    cb = const_brier(data)
    print(f"\n  {label}")
    print(f"    moeda 50%   {cb:.4f}")
    print(f"    modelo      {br:.4f}   acerto {ac*100:.1f}%   (n={n})")
    print(f"    diferenca   {br-cb:+.4f}  " +
          ("(modelo pior)" if br > cb else "(modelo melhor)"))

print()
print("=" * 68)
print("2. QUE DIFERENCA SERIA DETECTAVEL COM ESTA AMOSTRA?")
print("=" * 68)
from collections import Counter
cnt = Counter(m["map"] for m in CORE)
print(f"  {'mapa':<13} {'partidas':>9} {'min. detectavel (poder 80%)':>30}")
for mp, k in cnt.most_common():
    # diferenca de winrate detectavel vs 50%, teste bilateral alfa=.05
    # d = (1.96+0.84) * sqrt(p(1-p)/k)
    d = 2.80 * math.sqrt(0.25 / k)
    print(f"  {mp:<13} {k:>9} {'':>10}±{d*100:>5.1f} pp  (ou seja, {50-d*100:.0f}% a {50+d*100:.0f}%)")

tot = len(CORE)
d_all = 2.80 * math.sqrt(0.25 / tot)
print(f"\n  Mesmo somando tudo ({tot} partidas), o minimo detectavel e ±{d_all*100:.1f} pp.")

# quantas partidas por mapa seriam necessarias para pegar efeitos plausiveis
print("\n  partidas POR MAPA necessarias para detectar um efeito de:")
for eff in (0.03, 0.05, 0.08, 0.10, 0.15):
    need = 0.25 * (2.80 / eff) ** 2
    print(f"    {eff*100:>4.0f} pp  ->  {need:>6.0f} partidas naquele mapa")

print()
print("=" * 68)
print("3. QUANTO DO RESULTADO E IRREDUTIVEL?")
print("=" * 68)
# variancia observada entre mapas vs variancia esperada so por amostragem
from collections import defaultdict
by = defaultdict(list)
for m in CORE:
    by[m["map"]].append(1 if m["result"] == "W" else 0)
base = sum(sum(v) for v in by.values()) / sum(len(v) for v in by.values())
obs_var = sum(len(v) * (sum(v)/len(v) - base) ** 2 for v in by.values()) / sum(len(v) for v in by.values())
exp_var = base * (1 - base) * (len(by) - 1) / sum(len(v) for v in by.values())
print(f"  variancia observada entre mapas : {obs_var:.5f}")
print(f"  esperada so por amostragem      : {exp_var:.5f}")
tau2 = obs_var - exp_var
print(f"  variancia 'real' estimada (tau2) : {tau2:+.5f}")
if tau2 <= 0:
    print("  -> tau2 <= 0: a dispersao entre mapas e MENOR que o ruido de amostragem.")
    print("     A melhor estimativa da diferenca verdadeira entre mapas e ZERO.")
else:
    print(f"  -> desvio real entre mapas ~ {math.sqrt(tau2)*100:.1f} pp")
