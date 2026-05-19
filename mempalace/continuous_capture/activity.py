"""Activity recorder — every authenticated MCP call updates last_activity_at.

version: 0.1.1 — Phase 1A
spec ref: MemPalace_Continuous_Capture_Architecture_v1.0.md §4.1, §4.2

D-CC2 (ratified 2026-05-19): the activity surface is the MCP protocol itself.
Every authenticated tool call carries the session's bearer token (or OAuth-issued
JWT). We hash that token and record an activity pulse against the hash. The hash
is the session identity used throughout Phase 1.

Why hash and not store the token: the static bearer is a long-lived secret. We
never store secrets in operational tables — only hashes for identity matching.
SHA-256 with no salt is fine for identity-correlation purposes (we're not
authenticating with the hash, just keying activity).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path

from . import db as _db

logger = logging.getLogger("mempalace.continuous_capture.activity")


def hash_token(token: str) -> str:
    """SHA-256 hash of the bearer token. Stable, deterministic, never reversed."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def record(
    token_hash: str,
    *,
    method: str | None = None,
    thread_id: str | None = None,
    last_message_id: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Record an activity pulse for a session identified by token_hash.

    Idempotent on a per-token basis: first call inserts, subsequent calls update
    last_activity_at and activity_count.

    Safe to call from request handlers — no async; sqlite is synchronous but
    single-row updates against an indexed PK are sub-millisecond.

    method: the JSON-RPC method that triggered this pulse, e.g. 'tools/call' or
            'tools/list'. Stored in last_method for later analysis (e.g. did the
            session end on a write or a read?).
    """
    now = datetime.utcnow().isoformat(timespec="seconds")

    with _db.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO idle_session (
                token_hash, first_activity_at, last_activity_at,
                thread_id, last_message_id, last_method, activity_count,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 'active', ?, ?)
            ON CONFLICT(token_hash) DO UPDATE SET
                last_activity_at = excluded.last_activity_at,
                last_method      = COALESCE(excluded.last_method, idle_session.last_method),
                thread_id        = COALESCE(excluded.thread_id, idle_session.thread_id),
                last_message_id  = COALESCE(excluded.last_message_id, idle_session.last_message_id),
                activity_count   = idle_session.activity_count + 1,
                status           = CASE
                                     WHEN idle_session.status = 'idle_closed' THEN 'active'
                                     ELSE idle_session.status
                                   END,
                updated_at       = excluded.updated_at
            """,
            (token_hash, now, now, thread_id, last_message_id, method, now, now),
        )
        conn.commit()

    logger.debug(
        "activity recorded token_hash=%s... method=%s",
        token_hash[:8], method or "(none)",
    )


def get_session(token_hash: str, db_path: Path | None = None) -> dict | None:
    """Read the idle_session row for a token_hash. Returns None if absent."""
    with _db.connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM idle_session WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None
