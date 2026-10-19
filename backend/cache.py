import json
import sqlite3
from contextlib import contextmanager

from config import DB_PATH

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS puuids (
    riot_id TEXT PRIMARY KEY,
    puuid TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_matches (
    puuid TEXT NOT NULL,
    match_id TEXT NOT NULL,
    queue_id INTEGER NOT NULL,
    game_creation INTEGER NOT NULL,
    PRIMARY KEY (puuid, match_id)
);

CREATE TABLE IF NOT EXISTS timelines (
    match_id TEXT PRIMARY KEY,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rank_snapshots (
    puuid TEXT NOT NULL,
    captured_at INTEGER NOT NULL,
    tier TEXT NOT NULL,
    division TEXT NOT NULL,
    lp INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    PRIMARY KEY (puuid, captured_at)
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_cached_puuid(riot_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT puuid FROM puuids WHERE riot_id = ?", (riot_id,)).fetchone()
        return row[0] if row else None


def save_puuid(riot_id: str, puuid: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT OR REPLACE INTO puuids (riot_id, puuid) VALUES (?, ?)", (riot_id, puuid))


def get_cached_match_ids(puuid: str) -> set[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT match_id FROM account_matches WHERE puuid = ?", (puuid,)).fetchall()
        return {row[0] for row in rows}


def get_match(match_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT raw_json FROM matches WHERE match_id = ?", (match_id,)).fetchone()
        return json.loads(row[0]) if row else None


def save_match(puuid: str, match_id: str, raw_json: dict) -> None:
    game_creation = raw_json["info"]["gameCreation"]
    queue_id = raw_json["info"]["queueId"]
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO matches (match_id, raw_json) VALUES (?, ?)",
            (match_id, json.dumps(raw_json)),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO account_matches (puuid, match_id, queue_id, game_creation)
            VALUES (?, ?, ?, ?)
            """,
            (puuid, match_id, queue_id, game_creation),
        )


def get_all_cached_matches(puuid: str, queue_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT m.raw_json FROM matches m
            JOIN account_matches am ON am.match_id = m.match_id
            WHERE am.puuid = ? AND am.queue_id = ?
            ORDER BY am.game_creation DESC
            """,
            (puuid, queue_id),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]


def get_timeline(match_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT raw_json FROM timelines WHERE match_id = ?", (match_id,)).fetchone()
        return json.loads(row[0]) if row else None


def save_timeline(match_id: str, raw_json: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO timelines (match_id, raw_json) VALUES (?, ?)",
            (match_id, json.dumps(raw_json)),
        )


def get_latest_rank_snapshot(puuid: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT captured_at, tier, division, lp, wins, losses FROM rank_snapshots
            WHERE puuid = ? ORDER BY captured_at DESC LIMIT 1
            """,
            (puuid,),
        ).fetchone()
        if not row:
            return None
        return {
            "capturedAt": row[0],
            "tier": row[1],
            "division": row[2],
            "lp": row[3],
            "wins": row[4],
            "losses": row[5],
        }


def save_rank_snapshot(puuid: str, captured_at: int, tier: str, division: str, lp: int, wins: int, losses: int) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO rank_snapshots
                (puuid, captured_at, tier, division, lp, wins, losses)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (puuid, captured_at, tier, division, lp, wins, losses),
        )


def get_rank_history(puuid: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT captured_at, tier, division, lp, wins, losses FROM rank_snapshots
            WHERE puuid = ? ORDER BY captured_at ASC
            """,
            (puuid,),
        ).fetchall()
        return [
            {
                "capturedAt": row[0],
                "tier": row[1],
                "division": row[2],
                "lp": row[3],
                "wins": row[4],
                "losses": row[5],
            }
            for row in rows
        ]
