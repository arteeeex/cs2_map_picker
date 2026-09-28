"""Modelo v12 (regras do usuario, sem controles):
- so Premier; peso linear por posicao: partida mais antiga do lobby = 0, mais recente = 1
- vitoria (com saldo de rounds) + desempenho (indice K/D/ADR/rating de cada jogador
  do lobby contra a propria media), metade/metade
- K/D convertido em % pelo proprio dado: inclinacao resultado ~ desempenho
Mesmo calculo do template.html; aqui roda o walk-forward para conferir."""
import math, sys

MAPS = ["cs_italy", "cs_office", "de_ancient", "de_anubis", "de_basalt", "de_cache", "de_dust2",
        "de_inferno", "de_mirage", "de_nuke", "de_overpass", "de_train", "de_vertigo"]
NP = 13
FLOOR, GAMMA = 0.05, 1.5
KG, KM, KR, KF = 10, 8, 6, 6
POOL = 240 * 86400


def load(path):
    rows = []
    for ln in open(path, encoding="utf-8"):
        p = ln.strip().split(",")
        if len(p) < 7:
            continue
        teams, perf, j = p[4], {}, 0
        for i in range(NP):
            if teams[i] != "-":
                s = p[6][j:j + 2]; j += 2
                if s != "xx":
                    perf[i] = int(s)
        rows.append(dict(ts=int(p[0]) * 60 + 1690000000, map=MAPS[int(p[1])], a=int(p[2]), b=int(p[3]),
                         teams=teams, prem=p[5] == "1", perf=perf))
    rows.sort(key=lambda r: r["ts"])
    set_trail(rows, TRAIL)
    return rows


TRAIL = 50


def set_trail(rows, W):
    """lb[i] = media do indice do jogador i nas W partidas de Premier anteriores
    (minimo 10). W=0 desliga (usa a media do lobby inteiro, como na v12)."""
    hist = {}
    for r in rows:
        r["lb"] = {}
        if not r["prem"]:
            continue
        for i, v in r["perf"].items():
            h = hist.setdefault(i, [])
            if W and len(h) >= 10:
                xs = h[-W:]
                r["lb"][i] = sum(xs) / len(xs)
            h.append(v)


def orient(r, lobby):
    side = None
    for i in lobby:
        ch = r["teams"][i]
        if ch == "-":
            continue
        if side and side != ch:
            return None
        side = ch
    if not side:
        return None
    return side


def kish(ws):
    a = sum(ws); b = sum(w * w for w in ws)
    return a * a / b if b > 1e-12 else 0.0


def shrink(mean, n, prior, k):
    return prior if n <= 1e-9 or mean is None else (n * mean + k * prior) / (n + k)


def wmean(pairs):
    num = den = 0.0
    for v, w in pairs:
        num += v * w; den += w
    return num / den if den > 1e-12 else None


def build(hist, lobby):
    ms = []
    for r in hist:
        if not r["prem"]:
            continue
        side = orient(r, lobby)
        if not side:
            continue
        rw, rl = (r["a"], r["b"]) if side == "1" else (r["b"], r["a"])
        roster = {i for i in range(NP) if r["teams"][i] == side}
        inter = len(roster & lobby); uni = len(roster | lobby)
        wR = FLOOR + (1 - FLOOR) * (inter / uni) ** GAMMA
        perf = {i: r["perf"][i] for i in lobby if r["teams"][i] == side and i in r["perf"]}
        out = 1 if rw > rl else 0 if rl > rw else 0.5
        ms.append(dict(lb=r["lb"], ts=r["ts"], map=r["map"], rw=rw, rl=rl, out=out, rs=rw / (rw + rl) if rw + rl else .5,
                       wR=wR, perf=perf))
    n = len(ms)
    for i, m in enumerate(ms):
        m["wT"] = i / (n - 1) if n > 1 else 1.0
        m["q"] = .65 * m["out"] + .35 * m["rs"]
    q1 = wmean([(m["q"], m["wT"]) for m in ms if m["out"] == 1])
    q0 = wmean([(m["q"], m["wT"]) for m in ms if m["out"] == 0])
    if q1 is not None and q0 is not None and q1 - q0 > .05:
        for m in ms:
            m["q"] = min(max((m["q"] - q0) / (q1 - q0), -.2), 1.2)
    # media de desempenho de cada jogador do lobby (ponderada pela recencia)
    base = {}
    for i in lobby:
        base[i] = wmean([(m["perf"][i], m["wT"]) for m in ms if i in m["perf"]])
    for m in ms:
        if TRAIL:
            ds = [m["perf"][i] - m["lb"][i] for i in m["perf"] if i in m["lb"]]
        else:
            ds = [m["perf"][i] - base[i] for i in m["perf"] if base[i] is not None]
        m["D"] = sum(ds) / len(ds) if ds else None
    return ms


def rank(hist, lobby, now, kd_share=0.5, maps_only=None):
    ms = build(hist, lobby)
    if not ms:
        return {}, 0.5, 0.0
    wt = [m["wT"] for m in ms]
    tG = shrink(wmean([(m["q"], m["wT"]) for m in ms]), kish(wt), .5, KG)
    # inclinacao: quanto 1 ponto de desempenho acima da propria media vale em resultado
    dd = [(m["D"], m["q"], m["wT"]) for m in ms if m["D"] is not None and m["wT"] > 0]
    slope = 0.0
    if len(dd) > 20:
        sw = sum(w for _, _, w in dd)
        mx = sum(d * w for d, _, w in dd) / sw; my = sum(q * w for _, q, w in dd) / sw
        vx = sum(w * (d - mx) ** 2 for d, _, w in dd) / sw
        cxy = sum(w * (d - mx) * (q - my) for d, q, w in dd) / sw
        slope = max(cxy / vx, 0) if vx > 1e-9 else 0.0
    pool = {m["map"] for m in ms if now - m["ts"] <= POOL} or {m["map"] for m in ms}
    out = {}
    for mp in pool:
        if maps_only and mp not in maps_only:
            continue
        on = [m for m in ms if m["map"] == mp]
        tM = shrink(wmean([(m["q"], m["wT"]) for m in on]), kish([m["wT"] for m in on]), tG, KM)
        ws = [m["wT"] * m["wR"] for m in on]
        n3 = kish(ws)
        tR = shrink(wmean([(m["q"], w) for m, w in zip(on, ws)]), n3, tM, KR)
        dv = [(m["D"], w) for m, w in zip(on, ws) if m["D"] is not None]
        Z = 0.0
        if dv and sum(w for _, w in dv) > 1e-9:
            zn = kish([w for _, w in dv])
            Z = wmean(dv) * zn / (zn + KF)
        pKD = min(max(tG + slope * Z, .01), .99)
        p = (1 - kd_share) * tR + kd_share * pKD
        out[mp] = dict(p=p, tR=tR, pKD=pKD, Z=Z, n=n3)
    return out, tG, slope


if __name__ == "__main__":
    rows = load(sys.argv[1] if len(sys.argv) > 1 else "data/artifact_v4.csv")
    prem = [r for r in rows if r["prem"]]
    print("partidas", len(rows), "premier", len(prem))
    now = rows[-1]["ts"]
    # ranking atual para voce + KICK
    for lob in ({0, 1}, {0}):
        res, tG, sl = rank(rows, lob, now)
        print("lobby", sorted(lob), "base %.3f slope %.4f/pt" % (tG, sl))
        for mp, v in sorted(res.items(), key=lambda kv: -kv[1]["p"]):
            print("  %-11s %.3f  win %.3f  kd %.3f  Z %+.2f  n %.1f" % (mp, v["p"], v["tR"], v["pKD"], v["Z"], v["n"]))
