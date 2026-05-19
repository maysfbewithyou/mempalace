"""Beacon endpoint + async worker — Phase 1B.

version: 0.1.2 — Phase 1B
spec ref: MemPalace_Continuous_Capture_Architecture_v1.0.md §4.3

D-CC7 (ratified): /api/mempalace/beacon is unauthenticated. navigator.sendBeacon()
cannot set Authorization headers, so the token identity is in the payload as
token_hash. Dedup at the worker layer is the guard — an attacker forging beacons
can only cause duplicate diary-write attempts, which the convergence gate (§4.5)
handles.

Two pieces:
  - make_beacon_route(proxy_provider): Starlette POST handler that enqueues
    a diary_write_queue row and returns 204 No Content (sendBeacon best
    practice — beacon receivers must be terse and fast).
  - run_beacon_worker(proxy): asyncio task that drains unprocessed queue rows
    every BEACON_POLL_INTERVAL_S and calls diary_writer.write_diary for each.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from . import activity, db, diary_writer

logger = logging.getLogger("mempalace.continuous_capture.beacon")

BEACON_POLL_INTERVAL_S = int(os.environ.get("MEMPALACE_BEACON_POLL_INTERVAL_S", "5"))
BEACON_BATCH_SIZE = int(os.environ.get("MEMPALACE_BEACON_BATCH_SIZE", "50"))
BEACON_MAX_RETRIES = int(os.environ.get("MEMPALACE_BEACON_MAX_RETRIES", "3"))

# sendBeacon may send text/plain even though the payload is JSON. We accept
# either Content-Type and try to JSON-parse.
_VALID_TRIGGERS = frozenset(
    {"beforeunload", "pagehide", "idle_10min", "heartbeat_dead", "manual"}
)


def make_beacon_route(proxy_provider):
    """Closure returning the Starlette POST handler for /api/mempalace/beacon.

    proxy_provider is unused by the route itself (the route just enqueues)
    but accepted for signature symmetry with make_diary_write_route — the
    actual proxy call lives in the worker.
    """

    async def beacon(request: Request) -> Response:
        # sendBeacon often sends text/plain. Read raw bytes; try JSON parse.
        try:
            raw = await request.body()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            # Silent 204 — sendBeacon's whole point is fire-and-forget.
            # A malformed beacon shouldn't waste a worker cycle.
            logger.warning("beacon: malformed payload — dropping")
            return Response(status_code=204)

        if not isinstance(payload, dict):
            return Response(status_code=204)

        token_hash = payload.get("token_hash")
        trigger = payload.get("trigger", "beforeunload")
        thread_id = payload.get("thread_id")
        last_message_id = payload.get("last_message_id")

        if not token_hash or not isinstance(token_hash, str):
            return Response(status_code=204)
        if trigger not in _VALID_TRIGGERS:
            trigger = "beforeunload"  # default rather than reject — we never want to drop a real beacon

        # Enqueue. Idempotency at the worker: it checks idle_session for an
        # existing diary_drawer_id before writing a duplicate.
        try:
            with db.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO diary_write_queue
                        (token_hash, trigger, thread_id, last_message_id, received_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        token_hash,
                        trigger,
                        thread_id,
                        last_message_id,
                        datetime.utcnow().isoformat(timespec="seconds"),
                    ),
                )
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("beacon: enqueue failed (non-fatal): %s", exc)
            # Still 204 — beacon callers can't act on errors anyway.
            return Response(status_code=204)

        return Response(status_code=204)

    return beacon


# ── Worker ───────────────────────────────────────────────────────────────────


async def _process_one(proxy: Any, row: dict, db_path: Path | None = None) -> None:
    """Process one queue row — call proxy, update row, dedup against idle_session."""
    token_hash = row["token_hash"]
    trigger = row["trigger"]
    queue_id = row["id"]

    # Dedup check — has Phase 1A's sweeper or a prior worker iteration already
    # closed this session? If so, mark this row processed and skip.
    sess = activity.get_session(token_hash)
    if sess and sess.get("diary_drawer_id"):
        with db.connect(db_path) as conn:
            conn.execute(
                """
                UPDATE diary_write_queue
                   SET processed_at = ?, drawer_id = ?
                 WHERE id = ?
                """,
                (
                    datetime.utcnow().isoformat(timespec="seconds"),
                    sess["diary_drawer_id"],
                    queue_id,
                ),
            )
            conn.commit()
        logger.debug(
            "beacon worker: dedup skip token_hash=%s... drawer=%s",
            token_hash[:8], sess["diary_drawer_id"],
        )
        return

    # Build a minimal session_row if we have no activity history for this token
    # (e.g. a session that emitted a beacon but never made an MCP call — rare but
    # possible if the user opened Atrium and immediately closed it).
    if sess is None:
        now_iso = datetime.utcnow().isoformat(timespec="seconds")
        session_row = {
            "token_hash": token_hash,
            "first_activity_at": row.get("received_at", now_iso),
            "last_activity_at": row.get("received_at", now_iso),
            "thread_id": row.get("thread_id"),
            "last_message_id": row.get("last_message_id"),
            "last_method": "(beacon-only)",
            "activity_count": 0,
        }
    else:
        session_row = sess

    success, drawer_id, err = await diary_writer.write_diary(
        proxy,
        token_hash=token_hash,
        trigger=trigger,
        session_row=session_row,
    )

    with db.connect(db_path) as conn:
        if success:
            conn.execute(
                """
                UPDATE diary_write_queue
                   SET processed_at = ?, drawer_id = ?
                 WHERE id = ?
                """,
                (
                    datetime.utcnow().isoformat(timespec="seconds"),
                    drawer_id,
                    queue_id,
                ),
            )
            # Also reflect into idle_session if it exists
            if sess is not None:
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
        else:
            next_retry = (row.get("retry_count") or 0) + 1
            if next_retry >= BEACON_MAX_RETRIES:
                # Mark processed with an error so we stop trying — operator can
                # query failed rows later.
                conn.execute(
                    """
                    UPDATE diary_write_queue
                       SET processed_at = ?, retry_count = ?, last_error = ?
                     WHERE id = ?
                    """,
                    (
                        datetime.utcnow().isoformat(timespec="seconds"),
                        next_retry,
                        (err or "unknown")[:500],
                        queue_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE diary_write_queue
                       SET retry_count = ?, last_error = ?
                     WHERE id = ?
                    """,
                    (next_retry, (err or "unknown")[:500], queue_id),
                )
        conn.commit()


async def _drain_once(proxy: Any, db_path: Path | None = None) -> int:
    """One drain pass. Returns count of rows processed (incl. dedup skips)."""
    with db.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM diary_write_queue
             WHERE processed_at IS NULL
               AND retry_count < ?
             ORDER BY received_at ASC
             LIMIT ?
            """,
            (BEACON_MAX_RETRIES, BEACON_BATCH_SIZE),
        ).fetchall()
        candidates = [dict(r) for r in rows]
    if not candidates:
        return 0
    for row in candidates:
        await _process_one(proxy, row, db_path=db_path)
    return len(candidates)


async def run_beacon_worker(proxy: Any, db_path: Path | None = None) -> None:
    """Long-running worker loop. Cancelled on graceful shutdown."""
    logger.info(
        "beacon_worker started: interval=%ds batch=%d max_retries=%d",
        BEACON_POLL_INTERVAL_S, BEACON_BATCH_SIZE, BEACON_MAX_RETRIES,
    )
    while True:
        try:
            drained = await _drain_once(proxy, db_path=db_path)
            if drained:
                logger.info("beacon_worker: processed %d queue rows", drained)
        except asyncio.CancelledError:
            logger.info("beacon_worker: cancelled (graceful shutdown)")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("beacon_worker iteration failed: %s", exc)
        try:
            await asyncio.sleep(BEACON_POLL_INTERVAL_S)
        except asyncio.CancelledError:
            logger.info("beacon_worker: cancelled during sleep")
            raise
