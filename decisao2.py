import random, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calib_core import M, N, WARM, Y, predict
POOL = [2, 3, 5, 6, 7, 8, 9, 10, 11]
ANTIGO = dict(hl=99999, floor=0.05, gamma=1.5, kG=10, kM=8, kR=6, wR=0.35, beta=0.12, fS=6)

def teste(idx, P, rotulo, leak=False):
    pct, ys = [], []
    for i in idx:
        if M[i]["map"] not in POOL: continue
        ps = {m: predict(i, P, m, leak=leak) for m in POOL}
        meu = ps[M[i]["map"]]
        pct.append(sum(1 for m in POOL if ps[m] < meu) / (len(POOL) - 1)); ys.append(Y[i])
    def gap(y):
        c = [b for a, b in zip(pct, y) if a >= 2/3]; f = [b for a, b in zip(pct, y) if a <= 1/3]
        return sum(c)/len(c) - sum(f)/len(f), c, f
    g, c, f = gap(ys)
    rng = random.Random(1); R = 10000
    ge = sum(1 for _ in range(R) if gap(rng.sample(ys, len(ys)))[0] >= g)
    le = sum(1 for _ in range(R) if gap(rng.sample(ys, len(ys)))[0] <= g)
    p2 = min(1, 2 * min(ge, le) / R)
    print(f"  {rotulo:<44} topo {sum(c)/len(c)*100:5.1f}% (n={len(c):>3})  fundo {sum(f)/len(f)*100:5.1f}% (n={len(f):>3})"
          f"  dif {g*100:+5.1f} pp  p(bicaudal)={p2:.3f}")

todos = range(WARM, N)
eu    = [i for i in todos if (M[i]["m1"] | M[i]["m2"]) & 1]
sem   = [i for i in todos if not ((M[i]["m1"] | M[i]["m2"]) & 1)]
print(f"walk-forward completo: {len(todos)} partidas ({len(eu)} com voce, {len(sem)} sem)\n")
print("CONTROLE POSITIVO (modelo espia o resultado - TEM que dar positivo):")
teste(todos, ANTIGO, "com vazamento", leak=True)
print("\nTESTE REAL (so historico anterior):")
teste(todos, ANTIGO, "todas as partidas")
teste(eu,    ANTIGO, "so partidas com voce no lobby")
teste(sem,   ANTIGO, "so partidas sem voce")
