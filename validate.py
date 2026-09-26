"""Validacao da formula contra uma verdade conhecida.

Dois testes que realmente importam:

  A) CONVERGENCIA - com amostra grande o modelo tem de reproduzir a verdade
     (Spearman -> 1.0). Se nao converge, a formula esta errada.

  B) UTILIDADE EM AMOSTRA PEQUENA - com poucas partidas o modelo encolhido
     tem de errar MENOS que a taxa de vitoria bruta. E para isto que servem
     o encolhimento e o n_eff; se nao bate a taxa bruta, nao vale a pena.
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import MapPicker
from mappick.sources import synth

CFG = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "config.json"), encoding="utf-8"))
SCENARIOS = [
    ("solo", []),
    ("eu+joao", ["76561198000000002"]),
    ("eu+pedro", ["76561198000000003"]),
    ("eu+joao+pedro", ["76561198000000002", "76561198000000003"]),
    ("eu+lucas+rafa", ["76561198000000004", "76561198000000005"]),
]


def truth(mates):
    t = {}
    for mp, base in synth.TRUE_MAP_SKILL.items():
        p = base + sum(synth.TRUE_SYNERGY.get(x, {}).get(mp, 0.0) for x in mates)
        t[mp] = min(max(p, 0.05), 0.95)
    return t


def spearman(a, b):
    ra = {k: i for i, k in enumerate(sorted(a, key=lambda k: -a[k]))}
    rb = {k: i for i, k in enumerate(sorted(b, key=lambda k: -b[k]))}
    n = len(ra)
    d2 = sum((ra[k] - rb[k]) ** 2 for k in ra)
    return 1 - 6 * d2 / (n * (n * n - 1))


def build(n_matches, seed, days_back=300):
    db = os.path.join("data", f"val_{n_matches}_{seed}.db")
    if os.path.exists(db):
        os.remove(db)
    conn = store.connect(db)
    for m in synth.generate(n_matches=n_matches, seed=seed, days_back=days_back):
        store.upsert_match(conn, m)
    conn.commit()
    ms = store.load_matches(conn, synth.ME)
    conn.close()
    os.remove(db)
    return ms


def raw_rate(ms, mp, mates):
    """Taxa de vitoria bruta com o roster EXATO - a alternativa ingenua."""
    target = set(mates)
    sel = [m for m in ms if m["map"] == mp and (m["roster"] - {synth.ME}) == target]
    if not sel:
        sel = [m for m in ms if m["map"] == mp]
    if not sel:
        return 0.5
    return sum(1 for m in sel if m["result"] == "W") / len(sel)


print("=" * 68)
print("TESTE A - CONVERGENCIA (a formula esta certa?)")
print("=" * 68)
for n in [500, 2000, 8000, 25000]:
    ms = build(n, seed=11, days_back=300)
    # janela longa para nao descartar a amostra grande no teste de convergencia
    cfg = json.loads(json.dumps(CFG))
    cfg["model"]["half_life_days"] = 4000
    cfg["model"]["max_age_days"] = 5000
    picker = MapPicker(ms, synth.ME, cfg)
    rhos, errs = [], []
    for label, mates in SCENARIOS:
        res = picker.rank(mates)
        pred = {m["map"]: m["p_win"] for m in res["maps"]}
        tru = truth(mates)
        rhos.append(spearman(pred, tru))
        errs.append(statistics.mean(abs(pred[k] - tru[k]) for k in tru))
    print(f"  N={n:>6}  Spearman medio = {statistics.mean(rhos):+.3f}   "
          f"erro medio absoluto = {statistics.mean(errs)*100:4.1f} pp")

print()
print("=" * 68)
print("TESTE B - UTILIDADE EM AMOSTRA PEQUENA (modelo vs taxa bruta)")
print("=" * 68)
for n in [150, 300, 600]:
    m_err, r_err, m_rho, r_rho = [], [], [], []
    for seed in range(1, 16):
        ms = build(n, seed=seed, days_back=300)
        picker = MapPicker(ms, synth.ME, CFG)
        for label, mates in SCENARIOS:
            res = picker.rank(mates)
            pred = {m["map"]: m["p_win"] for m in res["maps"]}
            raw = {mp: raw_rate(ms, mp, mates) for mp in synth.MAPS}
            tru = truth(mates)
            m_err.append(statistics.mean(abs(pred[k] - tru[k]) for k in tru))
            r_err.append(statistics.mean(abs(raw[k] - tru[k]) for k in tru))
            m_rho.append(spearman(pred, tru))
            r_rho.append(spearman(raw, tru))
    print(f"  N={n:>4} (15 seeds x 5 cenarios)")
    print(f"     modelo     : erro {statistics.mean(m_err)*100:4.1f} pp   "
          f"Spearman {statistics.mean(m_rho):+.3f}")
    print(f"     taxa bruta : erro {statistics.mean(r_err)*100:4.1f} pp   "
          f"Spearman {statistics.mean(r_rho):+.3f}")
    gain = (statistics.mean(r_err) - statistics.mean(m_err)) * 100
    print(f"     -> modelo erra {gain:+.1f} pp a menos que a taxa bruta")
