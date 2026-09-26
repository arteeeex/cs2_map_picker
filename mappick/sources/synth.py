"""Gerador de historico sintetico.

Serve para duas coisas:
  1. testar a interface e o modelo antes de ligar a fonte real;
  2. VALIDAR a formula - geramos partidas a partir de forcas "verdadeiras"
     conhecidas e conferimos se o modelo recupera o ranking correto.
"""
import hashlib
import random
from datetime import datetime, timedelta, timezone

MAPS = ["de_ancient", "de_dust2", "de_inferno", "de_mirage",
        "de_nuke", "de_overpass", "de_train", "de_anubis"]

ME = "76561198000000001"
FRIENDS = {
    "76561198000000002": "joao",
    "76561198000000003": "pedro",
    "76561198000000004": "lucas",
    "76561198000000005": "rafa",
}

# "verdade" escondida que o modelo precisa redescobrir
TRUE_MAP_SKILL = {
    "de_mirage": 0.62, "de_inferno": 0.58, "de_dust2": 0.55, "de_ancient": 0.50,
    "de_nuke": 0.40, "de_overpass": 0.45, "de_train": 0.47, "de_anubis": 0.52,
}
# sinergia extra por colega, em pontos de probabilidade, por mapa
TRUE_SYNERGY = {
    "76561198000000002": {"de_nuke": +0.18, "de_mirage": +0.04},   # joao salva o nuke
    "76561198000000003": {"de_dust2": +0.10, "de_ancient": -0.08},
    "76561198000000004": {"de_inferno": +0.12},
    "76561198000000005": {"de_overpass": -0.10, "de_train": +0.06},
}


def _rng_for(seed):
    return random.Random(seed)


def generate(n_matches=400, days_back=300, seed=7):
    rng = _rng_for(seed)
    now = datetime.now(timezone.utc)
    matches = []
    for i in range(n_matches):
        mp = rng.choice(MAPS)
        squad_size = rng.choices([0, 1, 2, 3, 4], weights=[18, 30, 26, 16, 10])[0]
        mates = rng.sample(list(FRIENDS), squad_size)

        p = TRUE_MAP_SKILL[mp]
        for mate in mates:
            p += TRUE_SYNERGY.get(mate, {}).get(mp, 0.0)
        p = min(max(p, 0.05), 0.95)

        won = rng.random() < p
        if won:
            rw = 13
            rl = rng.choices([2, 5, 7, 9, 11, 12], weights=[6, 14, 20, 22, 20, 18])[0]
        else:
            rl = 13
            rw = rng.choices([2, 5, 7, 9, 11, 12], weights=[6, 14, 20, 22, 20, 18])[0]

        age = rng.random() ** 0.8 * days_back
        played = now - timedelta(days=age, hours=rng.random() * 24)

        players = []
        for sid in [ME] + mates:
            # performance correlacionada com o resultado + um vies por mapa
            base = 1.05 if sid == ME else rng.uniform(0.9, 1.15)
            bump = TRUE_SYNERGY.get(sid, {}).get(mp, 0.0) * 2.0
            form = base + bump + (0.12 if won else -0.12) + rng.gauss(0, 0.13)
            rounds = rw + rl
            kills = max(0, int(rounds * 0.72 * form + rng.gauss(0, 2)))
            deaths = max(1, int(rounds * 0.72 / max(form, 0.4) + rng.gauss(0, 2)))
            players.append({
                "steam64": sid,
                "name": "eu" if sid == ME else FRIENDS[sid],
                "is_ally": True,
                "kills": kills,
                "deaths": deaths,
                "assists": max(0, int(rng.gauss(rounds * 0.15, 2))),
                "adr": round(max(30.0, 78 * form + rng.gauss(0, 9)), 1),
                "kast": round(min(95.0, max(45.0, 70 * form + rng.gauss(0, 6))), 1),
                "hs_pct": round(min(80.0, max(20.0, rng.gauss(48, 9))), 1),
                "rating": round(max(0.2, form + rng.gauss(0, 0.05)), 2),
            })

        mid = hashlib.sha1(f"synth-{seed}-{i}".encode()).hexdigest()[:16]
        matches.append({
            "id": f"synth_{mid}", "source": "synth",
            "played_at": played.isoformat(), "map": mp, "mode": "premier",
            "rounds_won": rw, "rounds_lost": rl,
            "result": "W" if won else "L",
            "players": players, "raw": None,
        })
    return matches


def seed_db(conn, n_matches=400, seed=7):
    from .. import store
    for m in generate(n_matches=n_matches, seed=seed):
        store.upsert_match(conn, m)
    for sid, name in FRIENDS.items():
        conn.execute(
            "INSERT INTO players (steam64,name,is_friend,updated_at) VALUES (?,?,1,?) "
            "ON CONFLICT(steam64) DO UPDATE SET name=excluded.name, is_friend=1",
            (sid, name, datetime.now(timezone.utc).isoformat()))
    conn.execute(
        "INSERT INTO players (steam64,name,is_friend,updated_at) VALUES (?,?,0,?) "
        "ON CONFLICT(steam64) DO UPDATE SET name=excluded.name",
        (ME, "eu", datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return ME
