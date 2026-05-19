"""Idle sweeper — periodic asyncio task that finds idle sessions and triggers diary writes.

version: 0.1.1 — Phase 1A
spec ref: MemPalace_Continuous_Capture_Architecture_v1.0.md §4.2, §10

Cadence: every IDLE_SWEEP_INTERVAL_S (default 60s).
Idle threshold: IDLE_TIMEOUT_S (default 600s = 10 min) per kickoff.

Why a single async task vs node-cron:
- The wrapper container is Python/Starlette (Phase 2 v0.2 §A3). Adding Node.js
  to satisfy a "node-cron" reference would expand the container needlessly.
- asyncio.create_task in the lifespan startup is the established Python pattern
  for in-process scheduled work. It's also cancellable on graceful shutdown.

Why not threading.Timer or APScheduler:
- The wrapper is single-event-loop. asyncio is natural here.
- APScheduler would add a dep + persistence layer we don't need.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import db as _db
from . import diary_writer

logger = logging.getLogger("mempalace.continuous_capture.sweeper")

IDLE_SWEEP_INTERVAL_S = int(os.environ.get("MEMPALACE_IDLE_SWEEP_INTERVAL_S", "60"))
IDLE_TIMEOUT_S = int(os.environ.get("MEMPALACE_IDLE_TIMEOUT_S", "600"))
MAX_RETRIES = int(os.environ.get("MEMPALACE_IDLE_MAX_RETRIES", "3"))


async def _sweep_once(proxy: Any, db_path: Path | None = None) -> int:
    """One sweep pass. Returns count of diary writes attempted (success or fail).

    Selects active sessions whose last_activity_at is older than IDLE_TIMEOUT_S
    and has not yet exceeded MAX_RETRIES. For each, attempts a diary write and
    updates the session row.
    """
    threshold = (datetime.utcnow() - timedelta(seconds=IDLE_TIMEOUT_S)).isoformat(
        timespec="seconds"
    )

    with _db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM idle_session
            WHERE status = 'active'
              AND last_activity_at < ?
              AND retry_count < ?
            ORDER BY last_activity_at ASC
            LIMIT 50
            """,
            (threshold, MAX_RETRIES),
        ).fetchall()
        candidates = [dict(r) for r in rows]

    if not candidates:
        return 0

    attempts = 0
    for session_row in candidates:
        token_hash = session_row["token_hash"]
        attempts += 1
        success, drawer_id, err = await diary_writer.write_diary(
            proxy,
            token_hash=token_hash,
            trigger="idle_10min",
            session_row=session_row,
        )

        with _db.connect(db_path) as conn:
            if success:
                conn.execute(
                    """
                    UPDATE idle_session
                       SET status            = 'diary_written',
                           diary_written_at  = ?,
                           diary_drawer_id   = ?,
                           updated_at        = ?
                     WHERE token_hash = ?
                    """,
                    (
                        datetime.utcnow().isoformat(timespec="seconds"),
                        drawer_id,
                        datetime.utcnow().isoformat(timespec="seconds"),
                        token_hash,
                    ),
                )
                # Also log to the audit queue per §4.5 convergence model.
                conn.execute(
                    """
                    INSERT INTO diary_write_queue
                        (token_hash, trigger, thread_id, last_message_id,
                         received_at, processed_at, drawer_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        token_hash,
                        "idle_10min",
                        session_row.get("thread_id"),
                        session_row.get("last_message_id"),
                        datetime.utcnow().isoformat(timespec="seconds"),
                        datetime.utcnow().isoformat(timespec="seconds"),
                        drawer_id,
                    ),
                )
            else:
                next_retry = session_row.get("retry_count", 0) + 1
                final_status = "failed" if next_retry >= MAX_RETRIES else "active"
                conn.execute(
                    """
                    UPDATE idle_session
                       SET retry_count = ?,
                           last_error  = ?,
                           status      = ?,
                           updated_at  = ?
                     WHERE token_hash = ?
                    """,
                    (
                        next_retry,
                        (err or "unknown")[:500],
                        final_status,
                        datetime.utcnow().isoformat(timespec="seconds"),
                        token_hash,
                    ),
                )
            conn.commit()
    return attempts


async def run_sweeper(proxy: Any, db_path: Path | None = None) -> None:
    """Long-running sweeper loop. Started by lifespan; cancelled on shutdown.

    Catches and logs exceptions per iteration so a transient failure doesn't
    kill the loop. Sleeps even after a successful sweep so the cadence remains
    consistent.
    """
    logger.info(
        "idle_sweeper started: interval=%ds timeout=%ds max_retries=%d",
        IDLE_SWEEP_INTERVAL_S, IDLE_TIMEOUT_S, MAX_RETRIES,
    )
    while True:
        try:
            attempted = await _sweep_once(proxy, db_path=db_path)
            if attempted:
                logger.info("idle_sweeper: attempted %d diary writes", attempted)
        except asyncio.CancelledError:
            logger.info("idle_sweeper: cancelled (graceful shutdown)")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("idle_sweeper iteration failed: %s", exc)
        try:
            await asyncio.sleep(IDLE_SWEEP_INTERVAL_S)
        except asyncio.CancelledError:
            logger.info("idle_sweeper: cancelled during sleep (graceful shutdown)")
            raise
