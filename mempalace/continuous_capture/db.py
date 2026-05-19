"""SQLite schema for the Continuous Capture build.

version: 0.1.1 — Phase 1A
spec ref: MemPalace_Continuous_Capture_Architecture_v1.0.md §6

Three tables, all introduced in this migration so Phase 1B/1C don't need a
follow-up migration:

  idle_session       — Layer 1A. One row per active session, updated by activity
                       middleware on every authenticated MCP call. The idle
                       sweeper queries this table.

  diary_write_queue  — Layers 1A/1B/1C all funnel into this queue. Phase 1B's
                       beacon endpoint enqueues here; the worker drains it.
                       Phase 1A's sweeper currently writes diary entries
                       synchronously but logs every attempt here for audit.

  heartbeat          — Layer 1C. One row per heartbeat pulse. Dead-thread
                       detector queries this table.

Why SQLite and not Postgres
---------------------------
Per D-CC1 (ratified 2026-05-19): mempalace-fork's existing precedent is
ChromaDB + SQLite (palace_graph.py is sqlite). Single-writer wrapper per
Phase 2 v0.2 §A4 means no concurrency drama. Self-contained — Phase 0
doesn't need to verify a Postgres connection.

Location
--------
~/.mempalace/continuous_capture.db (parent dir owned by Phase 2 bootstrap)
Override via env: MEMPALACE_CC_DB_PATH (used by tests)
"""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("mempalace.continuous_capture.db")

SCHEMA_VERSION = 1  # bump on any schema migration

# Source of truth for the schema. Applied via _apply_schema().
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cc_schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

-- Layer 1A — Idle 10-minute timeout
CREATE TABLE IF NOT EXISTS idle_session (
    token_hash         TEXT PRIMARY KEY,
    first_activity_at  TIMESTAMP NOT NULL,
    last_activity_at   TIMESTAMP NOT NULL,
    thread_id          TEXT,
    last_message_id    TEXT,
    last_method        TEXT,                -- which MCP method touched this last
    activity_count     INTEGER NOT NULL DEFAULT 1,
    status             TEXT NOT NULL DEFAULT 'active',
    diary_written_at   TIMESTAMP,
    diary_drawer_id    TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT,
    created_at         TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at         TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_idle_session_status_last_activity
  ON idle_session(status, last_activity_at);

-- Layer 1B — beforeunload + sendBeacon (Phase 1B writes; Phase 1A also logs here for audit)
CREATE TABLE IF NOT EXISTS diary_write_queue (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash         TEXT NOT NULL,
    trigger            TEXT NOT NULL,           -- idle_10min | beforeunload | heartbeat_dead
    thread_id          TEXT,
    last_message_id    TEXT,
    received_at        TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    processed_at       TIMESTAMP,
    drawer_id          TEXT,
    retry_count        INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_dwq_unprocessed
  ON diary_write_queue(processed_at, received_at);

-- Layer 1C — Heartbeat with adaptive curve (Phase 1C populates; Phase 1A inserts the schema only)
CREATE TABLE IF NOT EXISTS heartbeat (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash              TEXT NOT NULL,
    thread_id               TEXT,
    pulse_at                TIMESTAMP NOT NULL,
    last_message_id         TEXT,
    user_state              TEXT,
    session_age_at_pulse_s  INTEGER NOT NULL,
    next_interval_s         INTEGER NOT NULL,
    state_changed           BOOLEAN NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_hb_token_pulse
  ON heartbeat(token_hash, pulse_at);
"""


def _default_db_path() -> Path:
    """Resolve the SQLite path with env override (tests use MEMPALACE_CC_DB_PATH)."""
    override = os.environ.get("MEMPALACE_CC_DB_PATH")
    if override:
        return Path(override)

    # Default: alongside the palace, in ~/.mempalace/
    palace_path = Path(os.environ.get("MEMPAL_PALACE_PATH", "/data/.mempalace/palace"))
    return palace_path.parent / "continuous_capture.db"


def init_db(db_path: Path | None = None) -> Path:
    """Create the SQLite file (if missing) and apply schema. Idempotent.

    Returns the resolved path so callers can confirm where the DB lives.

    Why idempotent: lifespan startup calls this on every container boot.
    We never want startup to fail because the DB already exists.
    """
    path = db_path if db_path is not None else _default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SCHEMA_SQL)
        # Record schema version for future migration tracking.
        conn.execute(
            "INSERT OR IGNORE INTO cc_schema_version(version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info("continuous_capture.db: schema v%d applied at %s", SCHEMA_VERSION, path)
    return path


@contextlib.contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a sqlite3.Connection.

    Uses row_factory=Row so callers can do row['column_name'] access.
    Caller is responsible for commit() — we do not auto-commit.

    Why not a connection pool: the wrapper is single-worker (Phase 2 v0.2 §A4)
    and sqlite handles single-process concurrent reads natively. The asyncio
    serialization happens at a higher layer where it matters.
    """
    path = db_path if db_path is not None else _default_db_path()
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit OFF, manual BEGIN/COMMIT
    conn.row_factory = sqlite3.Row
    # Enforce foreign keys (even though we have none yet, sets pattern for v0.2)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def schema_version(db_path: Path | None = None) -> int:
    """Return the highest applied schema version, or 0 if uninitialized."""
    path = db_path if db_path is not None else _default_db_path()
    if not path.exists():
        return 0
    with connect(path) as conn:
        row = conn.execute(
            "SELECT MAX(version) AS v FROM cc_schema_version"
        ).fetchone()
        return row["v"] or 0 if row else 0
