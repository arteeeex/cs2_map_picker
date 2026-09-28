"""Melhorias para o calculo da v12 que NAO espremem os numeros (o usuario rejeitou
o encolhimento forte da v13). Walk-forward 933 partidas + medida do espalhamento.
  A  v12 como esta publicada
  B  K/D contra o nivel do jogador na epoca (50 partidas anteriores), nao a media de sempre
  C  parte do K/D ancorada no nivel DESTE time (lineup), igual a parte de vitoria
  D  B + C"""
import math
import modelo as M


def rank_v(hist, lobby, now, base_lineup):
    ms = M.build(hist, lobby)
    if not ms:
        return {}
    wt = [m["wT"] for m in ms]
    tG = M.shrink(M.wmean([(m["q"], m["wT"]) for m in ms]), M.kish(wt), .5, M.KG)
    for m in ms:
        m["w"] = m["wT"] * m["wR"]
    tL = M.shrink(M.wmean([(m["q"], m["w"]) for m in ms]), M.kish([m["w"] for m in ms]), tG, M.KR)
    dd = [(m["D"], m["q"], m["wT"]) for m in ms if m["D"] is not None and m["wT"] > 0]
    slope = 0.0
    if len(dd) > 20:
        sw = sum(w for _, _, w in dd)
        mx = sum(d * w for d, _, w in dd) / sw; my = sum(q * w for _, q, w in dd) / sw
        vx = sum(w * (d - mx) ** 2 for d, _, w in dd) / sw
        cxy = sum(w * (d - mx) * (q - my) for d, q, w in dd) / sw
        slope = max(cxy / vx, 0) if vx > 1e-9 else 0.0
    pool = {m["map"] for m in ms if now - m["ts"] <= M.POOL} or {m["map"] for m in ms}
    base = tL if base_lineup else tG
    out = {}
    for mp in pool:
        on = [m for m in ms if m["map"] == mp]
        tM = M.shrink(M.wmean([(m["q"], m["wT"]) for m in on]), M.kish([m["wT"] for m in on]), tG, M.KM)
        ws = [m["w"] for m in on]
        n3 = M.kish(ws)
        tR = M.shrink(M.wmean([(m["q"], w) for m, w in zip(on, ws)]), n3, tM, M.KR)
        dv = [(m["D"], w) for m, w in zip(on, ws) if m["D"] is not None]
        Z = 0.0
        if dv:
            zn = M.kish([w for _, w in dv])
            Z = M.wmean(dv) * zn / (zn + M.KF)
        pKD = min(max(base + slope * Z, .01), .99)
        out[mp] = .5 * tR + .5 * pKD
    return out


def avalia(trail, base_lineup):
    M.TRAIL = trail
    rows = M.load("data/artifact_v4.csv")
    prem = [r for r in rows if r["prem"]]
    b, dec, spreads = [], [], []
    for t in prem[-1000:]:
        sides = {}
        for i in range(M.NP):
            if t["teams"][i] != "-":
                sides.setdefault(t["teams"][i], set()).add(i)
        if len(sides) != 1:
            continue
        side, lobby = next(iter(sides.items()))
        rw, rl = (t["a"], t["b"]) if side == "1" else (t["b"], t["a"])
        if rw == rl:
            continue
        y = 1 if rw > rl else 0
        o = rank_v([r for r in rows if r["ts"] < t["ts"]], lobby, t["ts"], base_lineup)
        if t["map"] not in o or len(o) < 5:
            continue
        b.append((o[t["map"]] - y) ** 2)
        order = sorted(o, key=lambda m: -o[m])
        dec.append((order.index(t["map"]) / (len(order) - 1), y))
        spreads.append(max(o.values()) - min(o.values()))
    top = [y for p, y in dec if p <= 1 / 3]; bot = [y for p, y in dec if p >= 2 / 3]
    a, c = sum(top) / len(top), sum(bot) / len(bot)
    se = math.sqrt(a * (1 - a) / len(top) + c * (1 - c) / len(bot))
    hoje = rank_v(rows, {0, 1}, rows[-1]["ts"], base_lineup)
    return (len(b), sum(b) / len(b), 100 * (a - c), 100 * se, 100 * sum(spreads) / len(spreads),
            sorted(((round(100 * v, 1), k[3:]) for k, v in hoje.items()), reverse=True))


for nome, trail, bl in (("A v12 publicada", 0, False), ("B nivel da epoca", 50, False),
                        ("C base do time", 0, True), ("D B + C", 50, True)):
    n, br, dif, se, sp, hoje = avalia(trail, bl)
    print("%-17s Brier %.5f  topo-fundo %+.1f pp (EP %.1f)  espalhamento medio %.1f pp" % (nome, br, dif, se, sp))
    print("   voce+KICK hoje:", " ".join("%s %.1f" % (m, p) for p, m in hoje))
