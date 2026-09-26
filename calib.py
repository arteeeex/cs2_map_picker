"""Calibracao objetiva de TODOS os parametros do modelo (13 jogadores).

Protocolo, para que o resultado nao seja subjetivo nem sobreajustado:
  1. Walk-forward: cada partida e prevista usando so as anteriores a ela.
  2. O lobby de cada previsao e quem do grupo jogou aquela partida.
  3. As previsoes sao divididas no tempo: as mais antigas (AJUSTE) servem
     para escolher os parametros; as mais recentes (VALIDACAO) nunca sao
     usadas na escolha - so para medir se a escolha generaliza.
  4. Busca por descida coordenada: um parametro por vez, varias passadas.
Metrica: Brier (erro quadratico da probabilidade). Menor e melhor.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
N_PLAYERS = 13
PERF = {"kd": 0.375, "adr": 0.375, "rating": 0.25}

# ------------------------------------------------------------------ dados
M = []
for line in open(os.path.join(HERE, "data", "artifact_u13.csv"), encoding="utf-8"):
    p = line.strip().split(",")
    if len(p) < 6 or not p[0]:
        continue
    if p[5] != "1":
        continue                                   # so Premier, como na pagina
    teams = p[4]
    m1 = m2 = 0
    for j, ch in enumerate(teams):
        if ch == "1": m1 |= 1 << j
        elif ch == "2": m2 |= 1 << j
    perf = None
    if len(p) >= 12 and p[6] != "":
        k, d, adr = float(p[6]), float(p[7]), float(p[9])
        rat = float(p[11]) if p[11] else None
        s = PERF["kd"] * min(k / max(d, 1), 3) / 3 + PERF["adr"] * min(adr, 150) / 150
        w = PERF["kd"] + PERF["adr"]
        if rat is not None:
            s += PERF["rating"] * min(rat, 2) / 2; w += PERF["rating"]
        perf = s / w
    M.append(dict(t=int(p[0]), map=int(p[1]), a=int(p[2]), b=int(p[3]),
                  m1=m1, m2=m2, eu1=(teams[0] == "1"), eu2=(teams[0] == "2"), perf=perf))
M.sort(key=lambda r: r["t"])
N = len(M)
WARM = 400
cut = WARM + int((N - WARM) * 0.6)
print(f"{N} partidas Premier | aquecimento {WARM} | AJUSTE {cut-WARM} | VALIDACAO {N-cut}")

POP = [bin(i).count("1") for i in range(1 << N_PLAYERS)]


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6); return math.log(p / (1 - p))


def sig(x):
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def predict(i, P):
    cur = M[i]
    L = cur["m1"] | cur["m2"]
    eu_no_lobby = bool(L & 1)
    hl, fl, ga = P["hl"], P["floor"], P["gamma"]
    wR = P["wR"]; wO = 1 - wR
    rows = []                      # (w, q_bruto, y, map, roster, perf)
    for h in M[:i]:
        s1, s2 = h["m1"] & L, h["m2"] & L
        if s1 and s2: continue
        if s1:   rw, rl, ros, eu = h["a"], h["b"], h["m1"], h["eu1"]
        elif s2: rw, rl, ros, eu = h["b"], h["a"], h["m2"], h["eu2"]
        else:    continue
        y = 1.0 if rw > rl else (0.0 if rl > rw else 0.5)
        tot = rw + rl
        rs = rw / tot if tot else 0.5
        w = 2 ** (-((cur["t"] - h["t"]) / 1440) / hl)
        rows.append((w, wO * y + wR * rs, y, h["map"], ros,
                     h["perf"] if (eu and eu_no_lobby) else None))
    if not rows:
        return 0.5
    # calibra q -> escala de vitoria
    sw1 = sq1 = sw0 = sq0 = 0.0
    for w, q, y, *_ in rows:
        if y == 1.0: sw1 += w; sq1 += w * q
        elif y == 0.0: sw0 += w; sq0 += w * q
    if sw1 > 0 and sw0 > 0 and (sq1 / sw1 - sq0 / sw0) > 0.05:
        q1, q0 = sq1 / sw1, sq0 / sw0
        qs = [min(max((q - q0) / (q1 - q0), -0.2), 1.2) for _, q, *_ in rows]
    else:
        qs = [q for _, q, *_ in rows]

    def lvl(idx, ws, prior, k):
        s1 = sum(ws)
        if s1 <= 0: return prior, 0.0
        s2 = sum(x * x for x in ws)
        n = s1 * s1 / s2
        mean = sum(qs[j] * ws[t] for t, j in enumerate(idx)) / s1
        return (n * mean + k * prior) / (n + k), n

    allw = [r[0] for r in rows]
    g, _ = lvl(range(len(rows)), allw, 0.5, P["kG"])
    mi = [j for j, r in enumerate(rows) if r[3] == cur["map"]]
    if not mi:
        return min(max(g, .02), .98)
    tm, _ = lvl(mi, [rows[j][0] for j in mi], g, P["kM"])
    lp = POP[L]
    rws = []
    for j in mi:
        ros = rows[j][4]
        jac = POP[ros & L] / POP[ros | L]
        rws.append(rows[j][0] * (fl + (1 - fl) * jac ** ga))
    tr, _ = lvl(mi, rws, tm, P["kR"])

    p = tr
    if P["beta"] and eu_no_lobby:
        allp = [(r[5], r[0]) for r in rows if r[5] is not None]
        if allp:
            den = sum(w for _, w in allp)
            mu = sum(v * w for v, w in allp) / den
            sd = max(math.sqrt(sum(w * (v - mu) ** 2 for v, w in allp) / den), 0.02)
            mp = [(rows[j][5], rows[j][0]) for j in mi if rows[j][5] is not None]
            if mp:
                d1 = sum(w for _, w in mp); d2 = sum(w * w for _, w in mp)
                mm = sum(v * w for v, w in mp) / d1
                zn = d1 * d1 / d2
                Z = ((mm - mu) / sd) * (zn / (zn + P["fS"]))
                p = sig(logit(tr) + P["beta"] * Z)
    return min(max(p, .02), .98)


def outcome(i):
    c = M[i]
    L = c["m1"] | c["m2"]
    rw, rl = (c["a"], c["b"]) if (c["m1"] & L) else (c["b"], c["a"])
    return 1.0 if rw > rl else (0.0 if rl > rw else 0.5)


Y = [outcome(i) for i in range(N)]


def brier(P, lo, hi, step=1):
    s = n = 0
    for i in range(lo, hi, step):
        s += (predict(i, P) - Y[i]) ** 2; n += 1
    return s / n


def acerto(P, lo, hi):
    h = n = 0
    for i in range(lo, hi):
        p = predict(i, P)
        if (p >= .5) == (Y[i] >= .5): h += 1
        n += 1
    return h / n


ATUAL = dict(hl=99999, floor=0.05, gamma=1.5, kG=10, kM=8, kR=6, wR=0.35, beta=0.12, fS=6)
GRID = {
    "hl":    [120, 240, 480, 960, 99999],
    "floor": [0.0, 0.02, 0.05, 0.1, 0.2, 0.4],
    "gamma": [0.5, 1.0, 1.5, 2.0, 3.0],
    "kG":    [2, 5, 10, 20, 40],
    "kM":    [2, 4, 8, 16, 32, 64],
    "kR":    [2, 3, 6, 12, 24, 48],
    "wR":    [0.0, 0.2, 0.35, 0.5, 0.7, 1.0],
    "beta":  [0.0, 0.06, 0.12, 0.25, 0.5],
    "fS":    [2, 6, 12, 24],
}

t0 = time.time()
b_atual = brier(ATUAL, WARM, cut)
print(f"\nparametros atuais no AJUSTE: {b_atual:.5f}  ({time.time()-t0:.0f}s por avaliacao)")
sys.stdout.flush()

best = dict(ATUAL); best_b = b_atual
for passada in (1, 2):
    mudou = False
    for k, vals in GRID.items():
        if k == "fS" and best["beta"] == 0:
            continue
        res = []
        for v in vals:
            P = dict(best); P[k] = v
            b = best_b if v == best[k] else brier(P, WARM, cut)
            res.append((b, v))
        b, v = min(res)
        linha = "  ".join(f"{vv}={bb:.5f}" for bb, vv in res)
        print(f"  [{passada}] {k:<6} {linha}")
        sys.stdout.flush()
        if v != best[k] and b < best_b - 1e-6:
            best[k] = v; best_b = b; mudou = True
    if not mudou:
        break

print("\n" + "=" * 70)
print("RESULTADO")
print("=" * 70)
print(f"  escolhido no AJUSTE: {best}")
moeda_v = sum((0.5 - Y[i]) ** 2 for i in range(cut, N)) / (N - cut)
ba, bb = brier(ATUAL, cut, N), brier(best, cut, N)
aa, ab = acerto(ATUAL, cut, N), acerto(best, cut, N)
print(f"\n  VALIDACAO ({N-cut} partidas que o ajuste nunca viu):")
print(f"    moeda 50%            Brier {moeda_v:.5f}   acerto 50.0%")
print(f"    parametros antigos   Brier {ba:.5f}   acerto {aa*100:.1f}%")
print(f"    parametros ajustados Brier {bb:.5f}   acerto {ab*100:.1f}%")
print(f"    -> ganho na validacao: {ba-bb:+.5f}")
json.dump({"best": best, "val_old": ba, "val_new": bb, "val_coin": moeda_v,
           "acc_old": aa, "acc_new": ab, "n_val": N - cut},
          open(os.path.join(HERE, "data", "calib_result.json"), "w"), indent=2)
print(f"\n  tempo total: {(time.time()-t0)/60:.1f} min")
