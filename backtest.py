"""Backtest walk-forward nos dados REAIS: o modelo preve melhor que o que?

Para cada partida i (em ordem cronologica), o modelo so enxerga as partidas
anteriores a i e preve a probabilidade de vitoria naquele mapa, com aquele
roster. Depois compara com o que de fato aconteceu.

Metrica: Brier score = media((p - resultado)^2). Menor e melhor.
  0.25 = chute de moeda (50% sempre)
Tambem reporta log-loss e acuracia.

Serve para duas coisas:
  1. saber se o modelo vale mais que olhar winrate;
  2. escolher os hiperparametros (meia-vida, piso de roster, encolhimentos)
     por evidencia, em vez de chute.
"""
import itertools
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import MapPicker, _parse_dt

CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "config.json"), encoding="utf-8"))
ME = CFG["me"]

conn = store.connect()
ALL = store.load_matches(conn, ME)
conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))
print(f"{len(ALL)} partidas reais\n")

WARMUP = 80          # precisa de algum historico antes de comecar a cobrar


def outcome(m):
    return 1.0 if m["result"] == "W" else (0.0 if m["result"] == "L" else 0.5)


def evaluate(cfg_model, verbose=False):
    """Roda o walk-forward e devolve (brier, logloss, acc, n)."""
    cfg = {**CFG, "model": {**CFG["model"], **cfg_model}}
    briers, lls, hits = [], [], []
    for i in range(WARMUP, len(ALL)):
        hist, cur = ALL[:i], ALL[i]
        # congela o "agora" no instante da partida avaliada: nada de espiar o futuro
        picker = MapPicker(hist, ME, cfg)
        picker.now = _parse_dt(cur["played_at"])
        picker.matches = picker._prepare(hist)
        picker._player_baselines = {}

        mates = {str(p) for p in cur["roster"]} - {ME}
        theta_g, _ = picker._level_global()
        theta_m, _ = picker._level_map(cur["map"], theta_g)
        theta_r, n_r, _ = picker._level_roster(cur["map"], mates, theta_m)
        z, _ = picker._form_z(ME, cur["map"])
        from mappick.model import logit, sigmoid
        p = sigmoid(logit(theta_r) + cfg["model"]["form_beta"] * z)

        y = outcome(cur)
        p = min(max(p, 1e-6), 1 - 1e-6)
        briers.append((p - y) ** 2)
        lls.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
        hits.append(1.0 if (p >= 0.5) == (y >= 0.5) else 0.0)
    n = len(briers)
    return sum(briers) / n, sum(lls) / n, sum(hits) / n, n


def baseline_const(v=0.5):
    b = [(v - outcome(ALL[i])) ** 2 for i in range(WARMUP, len(ALL))]
    return sum(b) / len(b)


def baseline_running(by_map=False, with_roster=False):
    """Winrate acumulado - a alternativa ingenua que o modelo precisa bater."""
    b = []
    for i in range(WARMUP, len(ALL)):
        hist, cur = ALL[:i], ALL[i]
        mates = {str(p) for p in cur["roster"]} - {ME}
        sel = hist
        if by_map:
            sel = [m for m in sel if m["map"] == cur["map"]]
        if with_roster:
            sel = [m for m in sel if ({str(p) for p in m["roster"]} - {ME}) == mates]
        p = (sum(outcome(m) for m in sel) / len(sel)) if sel else 0.5
        p = min(max(p, 0.02), 0.98)
        b.append((p - outcome(cur)) ** 2)
    return sum(b) / len(b)


print("=" * 66)
print("REFERENCIAS (Brier - menor e melhor)")
print("=" * 66)
print(f"  moeda (50% sempre)            {baseline_const():.4f}")
print(f"  winrate geral acumulado       {baseline_running():.4f}")
print(f"  winrate por mapa              {baseline_running(by_map=True):.4f}")
print(f"  winrate por mapa + roster     {baseline_running(by_map=True, with_roster=True):.4f}")

b, ll, acc, n = evaluate({})
print(f"\n  MODELO ATUAL                  {b:.4f}   logloss {ll:.4f}  acerto {acc*100:.1f}%  (n={n})")

print()
print("=" * 66)
print("BUSCA DE HIPERPARAMETROS (no backtest, nao no ajuste)")
print("=" * 66)
grid = {
    "half_life_days": [60, 120, 200, 365, 10000],
    "roster_floor": [0.05, 0.15, 0.35],
    "roster_sharpness": [1.0, 1.5],
    "shrink_map": [4, 8, 16],
    "shrink_roster": [3, 6, 12],
    "form_beta": [0.0, 0.12, 0.30],
}
keys = list(grid)
best, results = None, []
for combo in itertools.product(*(grid[k] for k in keys)):
    cfg_m = dict(zip(keys, combo))
    br, _, ac, _ = evaluate(cfg_m)
    results.append((br, ac, cfg_m))
    if best is None or br < best[0]:
        best = (br, ac, cfg_m)

results.sort(key=lambda r: r[0])
print("\n  melhores 8:")
for br, ac, c in results[:8]:
    print(f"    {br:.4f}  acerto {ac*100:4.1f}%  {c}")
print("\n  piores 3:")
for br, ac, c in results[-3:]:
    print(f"    {br:.4f}  acerto {ac*100:4.1f}%  {c}")

print(f"\n  ATUAL  {b:.4f}")
print(f"  MELHOR {best[0]:.4f}  ->  ganho de {(b-best[0]):.4f} ({(b-best[0])/b*100:.1f}%)")
print(f"         {best[2]}")

# efeito isolado de cada parametro, mantendo o resto no melhor achado
print("\n  sensibilidade (a partir do melhor):")
for k in keys:
    linha = []
    for v in grid[k]:
        cfg_m = {**best[2], k: v}
        br, _, _, _ = evaluate(cfg_m)
        linha.append(f"{v}={br:.4f}")
    print(f"    {k:<20} " + "  ".join(linha))
