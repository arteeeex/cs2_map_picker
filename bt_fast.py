"""Backtest rapido com os 760: o modelo finalmente bate a moeda?"""
import json, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import _parse_dt

CFG = json.load(open("config.json", encoding="utf-8")); ME = CFG["me"]
conn = store.connect(); ALL = store.load_matches(conn, ME); conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))
for m in ALL:
    m["_t"] = _parse_dt(m["played_at"]).timestamp()
    m["_mates"] = {str(p) for p in m["roster"]} - {ME}
    m["_y"] = 1.0 if m["result"]=="W" else (0.0 if m["result"]=="L" else 0.5)
    m["_rs"] = m["rounds_won"]/(m["rounds_won"]+m["rounds_lost"])

PREM = [m for m in ALL if (m.get("mode") or "")=="premier"]

def predict(hist, cur, hl=120, floor=.15, gamma=1.5, k1=10, k2=8, k3=6, use_rounds=True):
    if not hist: return 0.5
    now = cur["_t"]
    W, Q = [], []
    for m in hist:
        w = 2 ** (-((now-m["_t"])/86400)/hl)
        q = 0.65*m["_y"] + 0.35*m["_rs"] if use_rounds else m["_y"]
        W.append(w); Q.append(q)
    # calibra q -> escala de vitoria
    if use_rounds:
        qw=[q for q,m in zip(Q,hist) if m["_y"]==1]; ql=[q for q,m in zip(Q,hist) if m["_y"]==0]
        if qw and ql:
            a,b = sum(qw)/len(qw), sum(ql)/len(ql)
            if a-b > .05: Q = [min(max((q-b)/(a-b),-.2),1.2) for q in Q]
    def lvl(sel_idx, prior, k):
        if not sel_idx: return prior, 0.0
        ws=[W[i] for i in sel_idx]; s1=sum(ws); s2=sum(w*w for w in ws)
        if s1<=0: return prior, 0.0
        mean=sum(Q[i]*W[i] for i in sel_idx)/s1
        n=(s1*s1/s2) if s2>0 else 0
        return (n*mean+k*prior)/(n+k), n
    g,_ = lvl(range(len(hist)), 0.5, k1)
    mi = [i for i,m in enumerate(hist) if m["map"]==cur["map"]]
    mm,_ = lvl(mi, g, k2)
    # nivel roster: repondera W pela semelhanca
    tgt = cur["_mates"]
    if mi:
        ws=[]; qs=[]
        for i in mi:
            mates=hist[i]["_mates"]
            if not mates and not tgt: j=1.0
            else:
                u=len(mates|tgt); j=(len(mates&tgt)/u) if u else 1.0
            w=W[i]*(floor+(1-floor)*(j**gamma)); ws.append(w); qs.append(Q[i])
        s1=sum(ws); s2=sum(w*w for w in ws)
        if s1>0:
            mean=sum(q*w for q,w in zip(qs,ws))/s1; n=(s1*s1/s2) if s2>0 else 0
            rr=(n*mean+k3*mm)/(n+k3)
        else: rr=mm
    else: rr=mm
    return min(max(rr,0.02),0.98)

def evaluate(data, warmup, **kw):
    b=[]; hit=[]
    for i in range(warmup,len(data)):
        p=predict(data[:i], data[i], **kw); y=data[i]["_y"]
        b.append((p-y)**2); hit.append(1.0 if (p>=.5)==(y>=.5) else 0.0)
    return sum(b)/len(b), sum(hit)/len(hit), len(b)

for label, data, wu in (("TODAS (760)", ALL, 200), ("SO PREMIER (615)", PREM, 200)):
    cb = sum((0.5-m["_y"])**2 for m in data[wu:])/len(data[wu:])
    br, ac, n = evaluate(data, wu)
    br0,ac0,_ = evaluate(data, wu, use_rounds=False)
    print(f"\n{label}   (avaliando {n})")
    print(f"  moeda 50%                  {cb:.4f}")
    print(f"  modelo (alvo com rounds)   {br:.4f}  acerto {ac*100:.1f}%  {'MELHOR' if br<cb else 'pior'}")
    print(f"  modelo (alvo so V/D)       {br0:.4f}  acerto {ac0*100:.1f}%  {'MELHOR' if br0<cb else 'pior'}")

print("\nvarrendo meia-vida e piso de roster (so Premier):")
best=None
for hl in (60,120,240,480,99999):
    for floor in (0.05,0.15,0.35,1.0):
        br,ac,_ = evaluate(PREM, 200, hl=hl, floor=floor)
        if best is None or br<best[0]: best=(br,ac,hl,floor)
        print(f"  hl={hl:<6} floor={floor:<5} Brier={br:.4f} acerto={ac*100:.1f}%")
cb = sum((0.5-m["_y"])**2 for m in PREM[200:])/len(PREM[200:])
print(f"\n  moeda={cb:.4f}   melhor={best[0]:.4f} (hl={best[2]}, floor={best[3]}) "
      f"-> {'GANHO de %.4f' % (cb-best[0]) if best[0]<cb else 'sem ganho'}")
