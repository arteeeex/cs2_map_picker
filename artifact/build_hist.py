"""Gera a pagina final (historico + veredito) a partir de data/artifact_u13.csv."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MAPS = ["cs_italy", "cs_office", "de_ancient", "de_anubis", "de_basalt", "de_cache",
        "de_dust2", "de_inferno", "de_mirage", "de_nuke", "de_overpass", "de_train", "de_vertigo"]

# ordem TEM de bater com as 13 posicoes do campo `teams` do CSV
PLAYERS = [
    {"id": "76561198816645847", "nome": "resenha ou morte"},
    {"id": "76561198426648959", "nome": "KICK PRETTOWSKI"},
    {"id": "76561198799388505", "nome": "pissa"},
    {"id": "76561199039885619", "nome": "M&MNEM"},
    {"id": "76561198344042074", "nome": "Rick"},
    {"id": "76561198846885567", "nome": "apschnaider"},
    {"id": "76561198387977576", "nome": "LO$T"},
    {"id": "76561198930486338", "nome": "huzuni"},
    {"id": "76561199444011678", "nome": "Pblox"},
    {"id": "76561198960846576", "nome": "fã do RRR"},
    {"id": "76561198875454317", "nome": "zacaco"},
    {"id": "76561199019723868", "nome": "᲼᲼᲼"},
    {"id": "76561199157526849", "nome": "sarra"},
]

# resultado do teste de decisao (decisao2.py, walk-forward completo) e da
# calibracao (calib2.py). Se os dados mudarem, rodar os scripts de novo.
TESTE = {"n": 1658, "topo": 51.3, "fundo": 53.7, "dif": -2.4, "p": 0.44,
         "controle": 22.0, "nval": 664}

raw = open(os.path.join(ROOT, "data", "artifact_u13.csv"), encoding="utf-8").read().strip()
html = open(os.path.join(HERE, "template_hist.html"), encoding="utf-8").read()
html = (html.replace("__RAW__", json.dumps(raw))
            .replace("__MAPS__", json.dumps(MAPS))
            .replace("__PLAYERS__", json.dumps(PLAYERS, ensure_ascii=False))
            .replace("__TESTE__", json.dumps(TESTE)))
for ph in ("__RAW__", "__MAPS__", "__PLAYERS__", "__TESTE__"):
    assert ph not in html, ph
open(os.path.join(HERE, "mappick.html"), "w", encoding="utf-8").write(html)
print(f"{len(raw.splitlines())} partidas | {len(PLAYERS)} jogadores | {len(html)/1024:.0f} KB")
