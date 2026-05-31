"""SQLite storage for AIS positions and derived risk flags.

Single-file DB so ingestion and the dashboard share state with zero infra.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config, geo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    mmsi       TEXT NOT NULL,
    name       TEXT,
    ts         TEXT NOT NULL,          -- ISO-8601 UTC
    lat        REAL NOT NULL,
    lon        REAL NOT NULL,
    sog        REAL,                   -- speed over ground, knots
    cog        REAL,                   -- course over ground, degrees
    in_zone    INTEGER NOT NULL DEFAULT 0,
    over_limit INTEGER NOT NULL DEFAULT 0,
    in_season  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_positions_mmsi ON positions(mmsi);
CREATE INDEX IF NOT EXISTS idx_positions_ts   ON positions(ts);
CREATE INDEX IF NOT EXISTS idx_positions_zone ON positions(in_zone);
"""


@contextmanager
def connect(db_path: str = config.DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = config.DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def insert_position(
    conn: sqlite3.Connection,
    *,
    mmsi: str,
    name: str | None,
    lat: float,
    lon: float,
    sog: float | None,
    cog: float | None,
    ts: datetime | None = None,
) -> None:
    """Insert one position, computing zone/limit/season flags."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    z, ol, seas, _violation = geo.classify(lat, lon, sog, ts)
    conn.execute(
        """
        INSERT INTO positions (mmsi, name, ts, lat, lon, sog, cog,
                               in_zone, over_limit, in_season)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(mmsi),
            name,
            ts.astimezone(timezone.utc).isoformat(),
            lat,
            lon,
            sog,
            cog,
            int(z),
            int(ol),
            int(seas),
        ),
    )


def reset(db_path: str = config.DB_PATH) -> None:
    """Wipe all positions (used by the simulator for a clean demo snapshot)."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM positions")
