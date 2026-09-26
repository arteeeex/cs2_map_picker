"""Injeta os dados reais no template e gera o HTML final do artifact."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MAPS = ["cs_italy", "cs_office", "de_ancient", "de_anubis", "de_basalt",
        "de_cache", "de_dust2", "de_inferno", "de_mirage", "de_nuke",
        "de_overpass", "de_train", "de_vertigo"]

# ordem tem de bater com as 4 posicoes do campo roster do CSV
MATES = [
    {"id": "76561198426648959", "nome": "KICK PRETTOWSKI"},
    {"id": "76561198799388505", "nome": "pissa"},
    {"id": "76561199039885619", "nome": "M&MNEM"},
    {"id": "76561198344042074", "nome": "Rick"},
]

with open(os.path.join(ROOT, "data", "artifact_full.csv"), encoding="utf-8") as f:
    raw = f.read().strip()

# so os mapas realmente usados, para nao carregar indice morto
used = sorted({int(l.split(",")[1]) for l in raw.split("\n") if l.strip()})
print(f"{len(raw.splitlines())} partidas | mapas usados: {[MAPS[i] for i in used]}")

with open(os.path.join(HERE, "template.html"), encoding="utf-8") as f:
    html = f.read()

html = (html
        .replace("__RAW__", json.dumps(raw))
        .replace("__MAPS__", json.dumps(MAPS))
        .replace("__MATES__", json.dumps(MATES, ensure_ascii=False)))

assert "__RAW__" not in html and "__MAPS__" not in html and "__MATES__" not in html
out = os.path.join(HERE, "mappick.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"gerado: {out} ({len(html)/1024:.0f} KB)")
