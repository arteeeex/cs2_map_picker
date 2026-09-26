"""Calibracao com grade ampliada + decomposicao: de onde vem a previsao?

  (a) moeda: 50% sempre
  (b) so a base do lobby: ignora mapa e time (encolhimento infinito)
  (c) base + mapa
  (d) base + mapa + semelhanca de time (modelo completo)
Cada nivel e ajustado no AJUSTE e medido na VALIDACAO, que o ajuste nunca viu.
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calib_core import M, N, WARM, cut, Y, brier, acerto

INF = 1e9
t0 = time.time()

def descida(base, grid, lo, hi):
    best = dict(base); bb = brier(best, lo, hi)
    for _ in range(3):
        mudou = False
        for k, vals in grid.items():
            res = [(bb if v == best[k] else brier({**best, k: v}, lo, hi), v) for v in vals]
            b, v = min(res)
            if v != best[k] and b < bb - 1e-7:
                best[k] = v; bb = b; mudou = True
        if not mudou: break
    return best, bb

BASE = dict(hl=99999, floor=1.0, gamma=1.5, kG=10, kM=INF, kR=INF, wR=1.0, beta=0.0, fS=6)
niveis = {}

# (b) so base do lobby
gb = {"kG": [0, 2, 5, 10, 20, 40, 80, 160, INF], "hl": [240, 480, 960, 99999]}
niveis["b"] = descida(BASE, gb, WARM, cut)
print("(b) base do lobby   ", niveis["b"][0], f"{niveis['b'][1]:.5f}"); sys.stdout.flush()

# (c) + mapa
gc = {"kM": [8, 16, 32, 64, 128, 256, 512, 1024, INF], "kG": gb["kG"], "hl": gb["hl"]}
niveis["c"] = descida({**niveis["b"][0]}, gc, WARM, cut)
print("(c) + mapa          ", niveis["c"][0], f"{niveis['c'][1]:.5f}"); sys.stdout.flush()

# (d) + time
gd = {"kR": [6, 12, 24, 48, 96, 192, 384, 768, INF],
      "floor": [0.0, 0.05, 0.2, 0.4, 0.7, 1.0], "gamma": [0.5, 1.0, 1.5, 3.0],
      "kM": gc["kM"], "kG": gb["kG"], "hl": gb["hl"], "wR": [0.0, 0.35, 0.7, 1.0],
      "beta": [0.0, 0.12, 0.5]}
niveis["d"] = descida({**niveis["c"][0], "floor": 0.4, "kR": 48}, gd, WARM, cut)
print("(d) + time (completo)", niveis["d"][0], f"{niveis['d'][1]:.5f}"); sys.stdout.flush()

moeda = sum((0.5 - Y[i]) ** 2 for i in range(cut, N)) / (N - cut)
print("\n" + "=" * 72)
print(f"VALIDACAO - {N-cut} partidas mais recentes, nunca usadas no ajuste")
print("=" * 72)
print(f"  (a) moeda 50%                 Brier {moeda:.5f}   acerto 50.0%")
out = {"moeda": moeda}
for k, nome in (("b", "base do lobby"), ("c", "+ mapa"), ("d", "+ time (completo)")):
    P = niveis[k][0]
    b = brier(P, cut, N); a = acerto(P, cut, N)
    out[k] = {"P": P, "brier": b, "acerto": a}
    print(f"  ({k}) {nome:<24} Brier {b:.5f}   acerto {a*100:.1f}%")
print(f"\n  contribuicao do MAPA : {out['b']['brier']-out['c']['brier']:+.5f}")
print(f"  contribuicao do TIME : {out['c']['brier']-out['d']['brier']:+.5f}")
print(f"  contribuicao da BASE : {moeda-out['b']['brier']:+.5f}")
json.dump(out, open(os.path.join("data", "calib2_result.json"), "w"), indent=2, default=str)
print(f"\n  tempo total: {(time.time()-t0)/60:.1f} min")
