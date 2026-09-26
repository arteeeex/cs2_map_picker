"""Backtest do modelo SIMETRICO sobre as 992: os parametros ainda sao os melhores?"""
import math, os
PLAYERS=["76561198816645847","76561198426648959","76561198799388505",
         "76561199039885619","76561198344042074"]
ROWS=[]
for line in open(os.path.join("data","artifact_union.csv"), encoding="utf-8"):
    p=line.strip().split(",")
    if not p or not p[0]: continue
    ROWS.append(dict(ts=int(p[0]), map=int(p[1]), a=int(p[2]), b=int(p[3]),
                     teams=p[4], prem=p[5]=="1"))
ROWS.sort(key=lambda r:r["ts"])
PREM=[r for r in ROWS if r["prem"]]
print(f"{len(ROWS)} partidas | {len(PREM)} Premier")

def orient(r, lobby):
    side=None
    for i,ch in enumerate(r["teams"]):
        if ch=="-" or PLAYERS[i] not in lobby: continue
        if side and side!=ch: return None
        side=ch
    if not side: return None
    roster={PLAYERS[i] for i,ch in enumerate(r["teams"]) if ch==side}
    rw,rl=(r["a"],r["b"]) if side=="1" else (r["b"],r["a"])
    return rw,rl,roster

def logit(p): p=min(max(p,1e-6),1-1e-6); return math.log(p/(1-p))

def predict(hist, cur, lobby, hl, floor, gamma=1.5, k1=10,k2=8,k3=6):
    now=cur["ts"]; W=[];Q=[];RS=[];MP=[]
    for r in hist:
        o=orient(r,lobby)
        if not o: continue
        rw,rl,roster=o; tot=rw+rl
        y=1.0 if rw>rl else (0.0 if rl>rw else .5)
        W.append(2**(-((now-r["ts"])/86400)/hl))
        Q.append(.65*y+.35*(rw/tot if tot else .5))
        RS.append(roster); MP.append(r["map"])
    if not W: return .5
    ys=[1 if q>.7 else (0 if q<.3 else .5) for q in Q]
    qw=[q for q,y in zip(Q,ys) if y==1]; ql=[q for q,y in zip(Q,ys) if y==0]
    if qw and ql:
        A,B=sum(qw)/len(qw),sum(ql)/len(ql)
        if A-B>.05: Q=[min(max((q-B)/(A-B),-.2),1.2) for q in Q]
    def lvl(idx,prior,k,ws=None):
        if not idx: return prior
        w=[ws[i] if ws else W[i] for i in idx]; s1=sum(w); s2=sum(x*x for x in w)
        if s1<=0: return prior
        n=s1*s1/s2 if s2>0 else 0
        return (n*(sum(Q[i]*w[j] for j,i in enumerate(idx))/s1)+k*prior)/(n+k)
    g=lvl(range(len(W)),.5,k1)
    mi=[i for i in range(len(W)) if MP[i]==cur["map"]]
    mm=lvl(mi,g,k2)
    if mi:
        ws=[]
        for i in mi:
            inter=len(RS[i]&lobby); uni=len(RS[i]|lobby)
            j=inter/uni if uni else 1
            ws.append(W[i]*(floor+(1-floor)*(j**gamma)))
        s1=sum(ws); s2=sum(x*x for x in ws)
        if s1>0:
            n=s1*s1/s2; mean=sum(Q[i]*ws[j] for j,i in enumerate(mi))/s1
            rr=(n*mean+k3*mm)/(n+k3)
        else: rr=mm
    else: rr=mm
    return min(max(rr,.02),.98)

def run(data, hl, floor, warmup=300):
    b=[];h=[]
    for i in range(warmup,len(data)):
        cur=data[i]
        lobby={PLAYERS[j] for j,ch in enumerate(cur["teams"]) if ch!="-"}
        if not lobby: continue
        o=orient(cur,lobby)
        if not o: continue
        rw,rl,_=o
        y=1.0 if rw>rl else (0.0 if rl>rw else .5)
        p=predict(data[:i],cur,lobby,hl,floor)
        b.append((p-y)**2); h.append(1.0 if (p>=.5)==(y>=.5) else 0.0)
    return sum(b)/len(b), sum(h)/len(h), len(b)

base=None
print("\n  hl     floor   Brier    acerto")
for hl in (120,240,480,99999):
    for floor in (0.05,0.15,0.35):
        br,ac,n=run(PREM,hl,floor)
        flag=" <-- em uso" if (hl==480 and floor==0.05) else ""
        if base is None or br<base[0]: base=(br,hl,floor,ac)
        print(f"  {hl:<6} {floor:<6} {br:.4f}  {ac*100:5.1f}%{flag}")
# moeda
ys=[]
for cur in PREM[300:]:
    lobby={PLAYERS[j] for j,ch in enumerate(cur["teams"]) if ch!="-"}
    o=orient(cur,lobby)
    if o: ys.append(1.0 if o[0]>o[1] else (0.0 if o[1]>o[0] else .5))
print(f"\n  moeda 50%: {sum((.5-y)**2 for y in ys)/len(ys):.4f}")
print(f"  melhor: hl={base[1]} floor={base[2]} -> {base[0]:.4f} ({base[3]*100:.1f}%)")
