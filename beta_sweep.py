"""Qual o peso ideal de K/D/ADR/rating? Medido por backtest, nao chutado."""
import json, os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import _parse_dt

CFG = json.load(open("config.json", encoding="utf-8")); ME = CFG["me"]
conn = store.connect(); ALL = store.load_matches(conn, ME); conn.close()
ALL.sort(key=lambda m: _parse_dt(m["played_at"]))
for m in ALL:
    m["_t"]=_parse_dt(m["played_at"]).timestamp()
    m["_mt"]={str(p) for p in m["roster"]}-{ME}
    m["_y"]=1.0 if m["result"]=="W" else (0.0 if m["result"]=="L" else 0.5)
    m["_rs"]=m["rounds_won"]/(m["rounds_won"]+m["rounds_lost"])
    p=m["players"].get(ME) or {}
    parts=w=0.0
    if p.get("kills") is not None and p.get("deaths") is not None:
        parts+=.375*min(p["kills"]/max(p["deaths"],1),3)/3; w+=.375
    if p.get("adr") is not None: parts+=.375*min(p["adr"],150)/150; w+=.375
    if p.get("rating") is not None: parts+=.25*min(p["rating"],2)/2; w+=.25
    m["_perf"]=parts/w if w>0 else None
PREM=[m for m in ALL if (m.get("mode") or "")=="premier"]

HL, FLOOR, GAMMA, K1, K2, K3, FK = 480, .05, 1.5, 10, 8, 6, 6
def logit(p): p=min(max(p,1e-6),1-1e-6); return math.log(p/(1-p))
def sig(x): return 1/(1+math.exp(-x)) if x>=0 else math.exp(x)/(1+math.exp(x))

def predict(hist, cur, beta):
    if not hist: return 0.5
    now=cur["_t"]; W=[];Q=[]
    for m in hist:
        W.append(2**(-((now-m["_t"])/86400)/HL)); Q.append(.65*m["_y"]+.35*m["_rs"])
    qw=[q for q,m in zip(Q,hist) if m["_y"]==1]; ql=[q for q,m in zip(Q,hist) if m["_y"]==0]
    if qw and ql:
        a,b=sum(qw)/len(qw),sum(ql)/len(ql)
        if a-b>.05: Q=[min(max((q-b)/(a-b),-.2),1.2) for q in Q]
    def lvl(idx,prior,k):
        if not idx: return prior
        ws=[W[i] for i in idx]; s1=sum(ws); s2=sum(x*x for x in ws)
        if s1<=0: return prior
        n=s1*s1/s2 if s2>0 else 0
        return (n*(sum(Q[i]*W[i] for i in idx)/s1)+k*prior)/(n+k)
    g=lvl(range(len(hist)),.5,K1)
    mi=[i for i,m in enumerate(hist) if m["map"]==cur["map"]]
    mm=lvl(mi,g,K2)
    if mi:
        ws=[];qs=[]
        for i in mi:
            mt=hist[i]["_mt"]; tg=cur["_mt"]
            if not mt and not tg: j=1.0
            else:
                u=len(mt|tg); j=(len(mt&tg)/u) if u else 1.0
            ws.append(W[i]*(FLOOR+(1-FLOOR)*(j**GAMMA))); qs.append(Q[i])
        s1=sum(ws); s2=sum(x*x for x in ws)
        rr=((s1*s1/s2)*(sum(q*w for q,w in zip(qs,ws))/s1)+K3*mm)/((s1*s1/s2)+K3) if s1>0 and s2>0 else mm
    else: rr=mm
    if beta:
        vals=[(m["_perf"],W[i]) for i,m in enumerate(hist) if m["_perf"] is not None]
        if vals:
            den=sum(w for _,w in vals); mu=sum(v*w for v,w in vals)/den
            sd=max(math.sqrt(sum(w*(v-mu)**2 for v,w in vals)/den),.02)
            mv=[(hist[i]["_perf"],W[i]) for i in mi if hist[i]["_perf"] is not None]
            if mv:
                d2=sum(w for _,w in mv); s2b=sum(w*w for _,w in mv)
                mm2=sum(v*w for v,w in mv)/d2; n=(d2*d2/s2b) if s2b>0 else 0
                z=((mm2-mu)/sd)*(n/(n+FK))
                rr=sig(logit(rr)+beta*z)
    return min(max(rr,.02),.98)

print("varredura do peso do K/D/ADR/rating (615 partidas Premier, avaliando 415)\n")
print(f"  {'form_beta':>10} {'Brier':>8} {'acerto':>8}")
base=sum((.5-m["_y"])**2 for m in PREM[200:])/len(PREM[200:])
print(f"  {'moeda':>10} {base:>8.4f} {'50.0%':>8}")
best=None
for beta in (0.0,0.06,0.12,0.25,0.5,1.0,2.0):
    b=[];h=[]
    for i in range(200,len(PREM)):
        p=predict(PREM[:i],PREM[i],beta); y=PREM[i]["_y"]
        b.append((p-y)**2); h.append(1.0 if (p>=.5)==(y>=.5) else 0.0)
    br=sum(b)/len(b); ac=sum(h)/len(h)
    if best is None or br<best[0]: best=(br,beta,ac)
    print(f"  {beta:>10.2f} {br:>8.4f} {ac*100:>7.1f}%")
print(f"\n  melhor: beta={best[1]} (Brier {best[0]:.4f}, acerto {best[2]*100:.1f}%)")
print(f"  em uso hoje: beta={CFG['model']['form_beta']}")
