"""O teste que importa para o PICK: o modelo ordena bem os mapas?

Para cada partida da VALIDACAO, o modelo calcula a % de TODOS os mapas do pool
para aquele lobby (usando so o historico anterior), e ve em que posicao ficou o
mapa que de fato foi jogado. Depois compara o winrate real quando o mapa jogado
estava no terco de CIMA do ranking contra quando estava no terco de BAIXO.
Se o ranking tem valor, cima > baixo. Significancia por permutacao.
"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calib_core import M, N, WARM, cut, Y, predict

POOL = [2, 3, 5, 6, 7, 8, 9, 10, 11]   # ancient anubis cache dust2 inferno mirage nuke overpass train
NOME = {2:"ancient",3:"anubis",5:"cache",6:"dust2",7:"inferno",8:"mirage",9:"nuke",10:"overpass",11:"train"}

def avaliar(P, lo, hi, rotulo):
    pct, ys = [], []
    for i in range(lo, hi):
        if M[i]["map"] not in POOL: continue
        ps = {m: predict(i, P, m) for m in POOL}
        meu = ps[M[i]["map"]]
        abaixo = sum(1 for m in POOL if ps[m] < meu)
        pct.append(abaixo / (len(POOL) - 1)); ys.append(Y[i])
    n = len(ys)
    def gap(p, y):
        cima = [yy for pp, yy in zip(p, y) if pp >= 2/3]
        baixo = [yy for pp, yy in zip(p, y) if pp <= 1/3]
        return (sum(cima)/len(cima) if cima else 0.5) - (sum(baixo)/len(baixo) if baixo else 0.5), len(cima), len(baixo)
    g, nc, nb = gap(pct, ys)
    cima = [yy for pp, yy in zip(pct, ys) if pp >= 2/3]
    baixo = [yy for pp, yy in zip(pct, ys) if pp <= 1/3]
    rng = random.Random(3); hits = 0; R = 20000
    for _ in range(R):
        sh = ys[:]; rng.shuffle(sh)
        if gap(pct, sh)[0] >= g: hits += 1
    p = hits / R
    print(f"  {rotulo:<28} topo {sum(cima)/nc*100:5.1f}% (n={nc})   fundo {sum(baixo)/nb*100:5.1f}% (n={nb})"
          f"   diferenca {g*100:+5.1f} pp   p={p:.4f}")
    return {"topo": sum(cima)/nc, "fundo": sum(baixo)/nb, "n_topo": nc, "n_fundo": nb, "gap": g, "p": p}

if __name__ == "__main__":
    ANTIGO = dict(hl=99999, floor=0.05, gamma=1.5, kG=10, kM=8, kR=6, wR=0.35, beta=0.12, fS=6)
    AJUST1 = json.load(open(os.path.join("data", "calib_result.json")))["best"]
    print(f"VALIDACAO: {N-cut} partidas mais recentes (nunca vistas no ajuste)\n")
    res = {"antigo": avaliar(ANTIGO, cut, N, "parametros antigos"),
           "ajuste1": avaliar(AJUST1, cut, N, "ajustados (1a calibracao)")}
    json.dump(res, open(os.path.join("data", "decisao_result.json"), "w"), indent=2)
