"""Quanto K/D, ADR e rating estao realmente mexendo no numero de cada mapa."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mappick import store
from mappick.model import MapPicker

CFG = json.load(open("config.json", encoding="utf-8")); ME = CFG["me"]
conn = store.connect(); ms = store.load_matches(conn, ME); conn.close()

print("pesos do indice de performance:", CFG["perf_weights"])
print("form_beta (quanto esse indice pesa no resultado):", CFG["model"]["form_beta"])
print()

mates = ["76561198426648959"]   # KICK, o parceiro mais frequente
com = MapPicker(ms, ME, CFG).rank(mates)

cfg0 = json.loads(json.dumps(CFG)); cfg0["model"]["form_beta"] = 0.0
sem = {m["map"]: m for m in MapPicker(ms, ME, cfg0).rank(mates)["maps"]}

print(f"{'mapa':<13} {'K/D':>6} {'ADR':>6} {'rating':>7} {'z':>7} {'sem KD':>8} {'com KD':>8} {'efeito':>8}")
print("-"*70)
for m in com["maps"]:
    mp = m["map"]
    sel = [x for x in ms if x["map"] == mp]
    ps = [x["players"][ME] for x in sel if ME in x["players"]]
    if len(ps) < 20: continue
    kd  = sum(p["kills"] for p in ps)/max(sum(p["deaths"] for p in ps),1)
    adr = sum(p["adr"] for p in ps)/len(ps)
    rat = sum(p["rating"] for p in ps if p["rating"] is not None)/max(len([p for p in ps if p["rating"] is not None]),1)
    a, b = sem[mp]["p_win"]*100, m["p_win"]*100
    print(f"{mp:<13} {kd:>6.2f} {adr:>6.1f} {rat:>7.2f} {m['breakdown']['form_Z']:>+7.2f} "
          f"{a:>7.1f}% {b:>7.1f}% {b-a:>+7.2f} pp")
