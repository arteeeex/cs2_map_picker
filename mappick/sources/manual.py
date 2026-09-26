"""Importador manual: CSV ou JSON. Sempre funciona, nao depende de site nenhum.

CSV - uma linha por JOGADOR por partida (e assim que sai da maioria dos exports):

    match_id,date,map,rounds_won,rounds_lost,steam64,name,kills,deaths,assists,adr,kast,hs_pct,rating
    m001,2026-09-14T21:30:00,de_mirage,13,9,7656...001,eu,22,17,4,84.2,72.0,51.0,1.14
    m001,2026-09-14T21:30:00,de_mirage,13,9,7656...002,joao,19,18,6,77.1,70.5,44.0,1.02

O minimo aceito e: match_id, date, map, rounds_won, rounds_lost, steam64.
Tudo o mais e opcional - o modelo usa o que existir e ignora o resto.

JSON - lista de partidas no formato normalizado (ver store.upsert_match).
"""
import csv
import json
import os

from .. import store

REQUIRED = {"match_id", "date", "map", "rounds_won", "rounds_lost", "steam64"}
ALIASES = {
    "matchid": "match_id", "id": "match_id", "game_id": "match_id",
    "played_at": "date", "datetime": "date", "timestamp": "date",
    "map_name": "map", "mapa": "map",
    "rw": "rounds_won", "score": "rounds_won", "rounds_for": "rounds_won",
    "rl": "rounds_lost", "score_against": "rounds_lost", "rounds_against": "rounds_lost",
    "steamid": "steam64", "steam_id": "steam64", "steamid64": "steam64",
    "k": "kills", "d": "deaths", "a": "assists",
    "hs": "hs_pct", "headshot_pct": "hs_pct", "hltv": "rating", "rating2": "rating",
}


def _num(v, cast=float):
    if v is None or v == "":
        return None
    try:
        return cast(str(v).replace(",", ".").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _norm_map(m):
    m = (m or "").strip().lower().replace(" ", "_")
    if m and not m.startswith(("de_", "cs_", "ar_")):
        m = "de_" + m
    return m


def import_csv(conn, path, me=None):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 0

    # normaliza cabecalhos
    clean = []
    for r in rows:
        o = {}
        for k, v in r.items():
            if k is None:
                continue
            key = k.strip().lower().replace(" ", "_")
            o[ALIASES.get(key, key)] = v
        clean.append(o)

    missing = REQUIRED - set(clean[0])
    if missing:
        raise SystemExit(f"CSV sem as colunas obrigatorias: {sorted(missing)}\n"
                         f"colunas encontradas: {sorted(clean[0])}")

    groups = {}
    for r in clean:
        groups.setdefault(r["match_id"], []).append(r)

    n = 0
    for mid, rs in groups.items():
        head = rs[0]
        rw, rl = int(_num(head["rounds_won"], float) or 0), int(_num(head["rounds_lost"], float) or 0)
        result = head.get("result") or ("W" if rw > rl else "L" if rl > rw else "D")
        players = []
        for r in rs:
            ally = r.get("is_ally", "1")
            players.append({
                "steam64": str(r["steam64"]).strip(),
                "name": (r.get("name") or "").strip() or None,
                "is_ally": str(ally).strip().lower() not in ("0", "false", "no", "nao"),
                "kills": _num(r.get("kills"), int), "deaths": _num(r.get("deaths"), int),
                "assists": _num(r.get("assists"), int), "adr": _num(r.get("adr")),
                "kast": _num(r.get("kast")), "hs_pct": _num(r.get("hs_pct")),
                "rating": _num(r.get("rating")),
            })
        store.upsert_match(conn, {
            "id": f"man_{mid}", "source": "manual",
            "played_at": str(head["date"]).strip(), "map": _norm_map(head["map"]),
            "mode": head.get("mode"), "rounds_won": rw, "rounds_lost": rl,
            "result": str(result).strip().upper()[:1], "players": players, "raw": None,
        })
        n += 1
    return n


def import_json(conn, path, me=None):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = data.get("matches", [])
    n = 0
    for m in data:
        m = dict(m)
        m.setdefault("source", "manual")
        m.setdefault("id", f"man_{m.get('match_id') or n}")
        m["map"] = _norm_map(m.get("map"))
        m.setdefault("played_at", m.get("date"))
        if "result" not in m:
            m["result"] = ("W" if m["rounds_won"] > m["rounds_lost"]
                           else "L" if m["rounds_lost"] > m["rounds_won"] else "D")
        store.upsert_match(conn, m)
        n += 1
    return n


def import_file(conn, path, me=None):
    if not os.path.exists(path):
        raise SystemExit(f"arquivo nao encontrado: {path}")
    if path.lower().endswith(".json"):
        return import_json(conn, path, me)
    return import_csv(conn, path, me)
