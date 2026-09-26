"""Coletor Leetify - fonte SECUNDARIA.

Aviso honesto sobre cobertura: o Leetify so processa partidas a partir do
momento em que a conta e conectada a ele, entao o historico antigo costuma
faltar. Use o CSStats como fonte principal e o Leetify como complemento (ele
traz stats melhores - KAST, rating, preaim - nas partidas que tem).

Endpoint publico confirmado por sondagem:
    https://api-public.cs-prod.leetify.com/v3/profile?steam64_id=...
(/v1/profile responde "Cannot GET", /v3/profile responde "Not Found" para um
steam64 sem perfil - ou seja, a rota existe.)

O JSON do Leetify muda de forma com alguma frequencia, entao a normalizacao
abaixo procura os campos por varios nomes possiveis em vez de fixar um so.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .. import store

BASE = "https://api-public.cs-prod.leetify.com"
LEGACY = "https://api.leetify.com/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _first(d, *keys, default=None):
    """Primeiro campo presente, aceitando varios nomes."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def fetch_profile(steam64):
    urls = [
        f"{BASE}/v3/profile?steam64_id={urllib.parse.quote(str(steam64))}",
        f"{LEGACY}/profile/id/{steam64}",
    ]
    last = None
    for u in urls:
        try:
            return _get(u)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} em {u}"
        except Exception as e:
            last = f"{e} em {u}"
    raise SystemExit(f"leetify: nao consegui ler o perfil ({last}). "
                     "Confirme o steam64 e que o perfil e publico no Leetify.")


def fetch_match(game_id):
    for u in (f"{BASE}/v3/games/{game_id}", f"{LEGACY}/games/{game_id}"):
        try:
            return _get(u)
        except Exception:
            continue
    return None


def normalize(game, me):
    """Converte um jogo do Leetify para o schema interno. Tolerante a formato."""
    me = str(me)
    gid = str(_first(game, "id", "gameId", "game_id", default="") or "")
    map_name = _first(game, "mapName", "map_name", "map", default=None)
    played = _first(game, "finishedAt", "gameFinishedAt", "finished_at", "date")
    if not gid or not map_name or not played:
        return None

    stats = (_first(game, "playerStats", "player_stats", "players", "stats", default=[]) or [])
    if not isinstance(stats, list) or not stats:
        return None

    mine = next((p for p in stats
                 if str(_first(p, "steam64Id", "steam64_id", "steamId", "steam_id",
                               default="")) == me), None)
    if mine is None:
        return None
    my_team = _first(mine, "initialTeamNumber", "teamNumber", "team_number", "team")

    players = []
    for p in stats:
        sid = str(_first(p, "steam64Id", "steam64_id", "steamId", "steam_id", default=""))
        if not sid:
            continue
        team = _first(p, "initialTeamNumber", "teamNumber", "team_number", "team")
        kast = _first(p, "kast", "kastPercentage")
        if kast is not None and kast <= 1.5:
            kast *= 100
        players.append({
            "steam64": sid,
            "name": _first(p, "name", "nickname", "playerName"),
            "is_ally": team == my_team,
            "kills": _first(p, "totalKills", "kills"),
            "deaths": _first(p, "totalDeaths", "deaths"),
            "assists": _first(p, "totalAssists", "assists"),
            "adr": _first(p, "dpr", "adr", "damagePerRound", "totalDamagePerRound"),
            "kast": kast,
            "hs_pct": _first(p, "hsPercentage", "hs_percentage", "headshotPercentage"),
            "rating": _first(p, "leetifyRating", "rating", "ctLeetifyRating"),
        })

    rw = _first(game, "teamScores", "scores", default=None)
    tw = _first(game, "matchResult", "result", default=None)
    rounds_won = _first(game, "roundsWon", "rounds_won")
    rounds_lost = _first(game, "roundsLost", "rounds_lost")
    if rounds_won is None and isinstance(rw, list) and len(rw) == 2:
        a, b = rw
        rounds_won, rounds_lost = (a, b) if my_team in (0, "0", 2) else (b, a)
    if rounds_won is None or rounds_lost is None:
        if isinstance(tw, str):
            rounds_won, rounds_lost = (13, 0) if tw.lower().startswith("win") else (0, 13)
        else:
            return None

    rounds_won, rounds_lost = int(rounds_won), int(rounds_lost)
    return {
        "id": f"lt_{gid}", "source": "leetify",
        "played_at": str(played), "map": str(map_name).lower(),
        "mode": _first(game, "dataSource", "gameMode", "mode"),
        "rounds_won": rounds_won, "rounds_lost": rounds_lost,
        "result": "W" if rounds_won > rounds_lost else "L" if rounds_lost > rounds_won else "D",
        "players": players, "raw": None,
    }


def sync(conn, steam64, verbose=False, delay=0.6, limit=None):
    steam64 = str(steam64)
    prof = fetch_profile(steam64)
    games = (_first(prof, "games", "matches", "recentGames", default=[]) or [])
    if verbose:
        print(f"leetify: {len(games)} partidas no perfil")
        if len(games) < 30:
            print("  (cobertura curta - normal: o Leetify so guarda a partir de "
                  "quando a conta foi conectada)")
    have = {r["id"] for r in conn.execute("SELECT id FROM matches WHERE source='leetify'")}
    n = 0
    for k, g in enumerate(games if limit is None else games[:limit], 1):
        norm = normalize(g, steam64)
        if norm is None:
            gid = _first(g, "id", "gameId", "game_id")
            if gid:
                full = fetch_match(gid)
                norm = normalize(full, steam64) if full else None
                time.sleep(delay)
        if norm is None or norm["id"] in have:
            continue
        store.upsert_match(conn, norm)
        n += 1
        if verbose and k % 20 == 0:
            print(f"  [{k}] ok")
    conn.commit()
    return n
