"""Armazenamento normalizado das partidas (SQLite, zero dependencias).

Schema deliberadamente agnostico a fonte: Leetify, CSStats, import manual e o
gerador sintetico escrevem todos na mesma forma, e o modelo so enxerga isto.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "matches.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    played_at    TEXT NOT NULL,          -- ISO8601 UTC
    map          TEXT NOT NULL,
    mode         TEXT,                   -- premier / competitive / wingman / ...
    rounds_won   INTEGER NOT NULL,
    rounds_lost  INTEGER NOT NULL,
    result       TEXT NOT NULL,          -- W / L / D
    dedupe_key   TEXT,                   -- mapa|dia|placar: mesma partida vinda de 2 fontes
    raw          TEXT
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id  TEXT NOT NULL,
    steam64   TEXT NOT NULL,
    name      TEXT,
    is_ally   INTEGER NOT NULL DEFAULT 1, -- 1 = meu time, 0 = adversario
    kills     INTEGER,
    deaths    INTEGER,
    assists   INTEGER,
    adr       REAL,
    kast      REAL,
    hs_pct    REAL,
    rating    REAL,
    PRIMARY KEY (match_id, steam64),
    FOREIGN KEY (match_id) REFERENCES matches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS players (
    steam64   TEXT PRIMARY KEY,
    name      TEXT,
    is_friend INTEGER NOT NULL DEFAULT 0,  -- aparece na UI de lobby
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_matches_map  ON matches(map);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(played_at);
CREATE INDEX IF NOT EXISTS idx_mp_steam     ON match_players(steam64);
"""


def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    # migracao: bancos criados antes da coluna de deduplicacao
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(matches)")}
    if "dedupe_key" not in cols:
        conn.execute("ALTER TABLE matches ADD COLUMN dedupe_key TEXT")
        conn.commit()
    return conn


def dedupe_key(match):
    """Identidade natural de uma partida, independente da fonte.

    Mesma partida vinda do CSStats e do Leetify tem id diferente mas e o mesmo
    jogo. Mapa + dia + placar ja e praticamente unico (colidiria so se voce
    jogasse o mesmo mapa com o mesmo placar duas vezes no mesmo dia).
    """
    day = str(match["played_at"])[:10]
    return f"{match['map']}|{day}|{match['rounds_won']}-{match['rounds_lost']}"


def upsert_match(conn, match):
    """match: dict normalizado. Idempotente - reimportar nao duplica."""
    conn.execute(
        """INSERT INTO matches (id, source, played_at, map, mode, rounds_won, rounds_lost,
                                result, dedupe_key, raw)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             played_at=excluded.played_at, map=excluded.map, mode=excluded.mode,
             rounds_won=excluded.rounds_won, rounds_lost=excluded.rounds_lost,
             result=excluded.result, dedupe_key=excluded.dedupe_key, raw=excluded.raw""",
        (match["id"], match["source"], match["played_at"], match["map"], match.get("mode"),
         match["rounds_won"], match["rounds_lost"], match["result"], dedupe_key(match),
         json.dumps(match.get("raw")) if match.get("raw") is not None else None),
    )
    conn.execute("DELETE FROM match_players WHERE match_id = ?", (match["id"],))
    for p in match.get("players", []):
        conn.execute(
            """INSERT INTO match_players
               (match_id, steam64, name, is_ally, kills, deaths, assists, adr, kast, hs_pct, rating)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (match["id"], str(p["steam64"]), p.get("name"), 1 if p.get("is_ally", True) else 0,
             p.get("kills"), p.get("deaths"), p.get("assists"),
             p.get("adr"), p.get("kast"), p.get("hs_pct"), p.get("rating")),
        )
        if p.get("is_ally", True):
            conn.execute(
                """INSERT INTO players (steam64, name, is_friend, updated_at) VALUES (?,?,0,?)
                   ON CONFLICT(steam64) DO UPDATE SET
                     name = COALESCE(excluded.name, players.name), updated_at = excluded.updated_at""",
                (str(p["steam64"]), p.get("name"), datetime.now(timezone.utc).isoformat()),
            )


def dedupe(conn, verbose=False):
    """Remove partidas repetidas entre fontes, ficando com a mais completa.

    Qualidade = quantos campos de estatistica vieram preenchidos. Na pratica o
    Leetify ganha do CSStats quando tem a partida (traz KAST e rating), e o
    CSStats cobre o resto do historico.
    """
    rows = conn.execute(
        """SELECT m.id, m.dedupe_key, m.source,
                  COUNT(mp.steam64) AS n_players,
                  SUM((mp.kills IS NOT NULL) + (mp.adr IS NOT NULL)
                      + (mp.kast IS NOT NULL) + (mp.rating IS NOT NULL)) AS filled
           FROM matches m LEFT JOIN match_players mp ON mp.match_id = m.id
           WHERE m.dedupe_key IS NOT NULL
           GROUP BY m.id"""
    ).fetchall()
    by_key = {}
    for r in rows:
        by_key.setdefault(r["dedupe_key"], []).append(r)

    removed = 0
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (-(r["filled"] or 0), -(r["n_players"] or 0), r["id"]))
        for loser in group[1:]:
            conn.execute("DELETE FROM match_players WHERE match_id = ?", (loser["id"],))
            conn.execute("DELETE FROM matches WHERE id = ?", (loser["id"],))
            removed += 1
            if verbose:
                print(f"  dedupe: {loser['id']} ({loser['source']}) removida, "
                      f"fica {group[0]['id']} ({group[0]['source']})")
    conn.commit()
    return removed


def backfill_dedupe_keys(conn):
    """Preenche dedupe_key em bancos criados antes dessa coluna existir."""
    rows = conn.execute(
        "SELECT id, map, played_at, rounds_won, rounds_lost FROM matches "
        "WHERE dedupe_key IS NULL").fetchall()
    for r in rows:
        conn.execute("UPDATE matches SET dedupe_key = ? WHERE id = ?",
                     (dedupe_key(dict(r)), r["id"]))
    conn.commit()
    return len(rows)


def load_matches(conn, me):
    """Devolve as partidas com o roster aliado ja montado, prontas para o modelo."""
    rows = conn.execute("SELECT * FROM matches ORDER BY played_at DESC").fetchall()
    out = []
    for r in rows:
        players = conn.execute(
            "SELECT * FROM match_players WHERE match_id = ? AND is_ally = 1", (r["id"],)
        ).fetchall()
        allies = {str(p["steam64"]) for p in players}
        if me and me not in allies:
            continue  # partida em que eu nao joguei
        out.append({
            "id": r["id"], "played_at": r["played_at"], "map": r["map"], "mode": r["mode"],
            "rounds_won": r["rounds_won"], "rounds_lost": r["rounds_lost"], "result": r["result"],
            "roster": allies,
            "players": {str(p["steam64"]): dict(p) for p in players},
        })
    return out


def known_players(conn, me=None):
    """Colegas descobertos no historico, do mais jogado para o menos.

    Inclui a ultima vez que voce jogou com a pessoa: em Premier solo a maior
    parte dessa lista sao randoms de uma partida so, e a interface usa esses
    dois numeros para separar quem e time de quem foi de passagem.
    """
    rows = conn.execute(
        """SELECT p.steam64, p.name, p.is_friend,
                  COUNT(mp.match_id) AS games,
                  MAX(m.played_at)   AS last_played
           FROM players p
           LEFT JOIN match_players mp ON mp.steam64 = p.steam64 AND mp.is_ally = 1
           LEFT JOIN matches m        ON m.id = mp.match_id
           GROUP BY p.steam64
           ORDER BY p.is_friend DESC, games DESC"""
    ).fetchall()
    return [dict(r) for r in rows if str(r["steam64"]) != str(me)]


def set_friend(conn, steam64, is_friend=True):
    conn.execute("UPDATE players SET is_friend=? WHERE steam64=?",
                 (1 if is_friend else 0, str(steam64)))
    conn.commit()
    return conn.total_changes
