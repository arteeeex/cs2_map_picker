"""Monta artifact/mappick.html a partir do template.html + data/artifact_v4.csv."""
import json, os

AQUI = os.path.dirname(os.path.abspath(__file__))
MAPS = ["cs_italy", "cs_office", "de_ancient", "de_anubis", "de_basalt", "de_cache", "de_dust2",
        "de_inferno", "de_mirage", "de_nuke", "de_overpass", "de_train", "de_vertigo"]
# ordem = ordem dos 13 caracteres do campo "times" na coleta
PLAYERS = [
    ("76561198816645847", "resenha ou morte"), ("76561198426648959", "KICK PRETTOWSKI"),
    ("76561198799388505", "pissa"), ("76561199039885619", "M&MNEM"), ("76561198344042074", "Rick"),
    ("76561198846885567", "apschnaider"), ("76561198387977576", "LO$T"), ("76561198930486338", "huzuni"),
    ("76561199444011678", "Pblox"), ("76561198960846576", "fã do RRR"), ("76561198875454317", "zacaco"),
    ("76561199019723868", "᲼᲼᲼ …3868"), ("76561199157526849", "sarra"),
]

tpl = open(os.path.join(AQUI, "template.html"), encoding="utf-8").read()
raw = open(os.path.join(AQUI, "..", "data", "artifact_v4.csv"), encoding="utf-8").read().strip()
html = (tpl.replace("__RAW__", json.dumps(raw))
           .replace("__MAPS__", json.dumps(MAPS))
           .replace("__PLAYERS__", json.dumps([{"id": i, "nome": n} for i, n in PLAYERS], ensure_ascii=False)))
open(os.path.join(AQUI, "mappick.html"), "w", encoding="utf-8", newline="\n").write(html)
print("ok", len(raw.splitlines()), "partidas,", len(html), "bytes")
