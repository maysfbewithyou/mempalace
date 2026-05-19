"""Heartbeat endpoint + dead-thread detector — Phase 1C.

version: 0.1.3 — Phase 1C
spec ref: MemPalace_Continuous_Capture_Architecture_v1.0.md §4.4

D-CC8 (ratified): initial cadence curve is 180s (0-3min) → 300s (3-15min)
→ 120s (15+min). The Heartbeat Optimizer (Phase 3.1) refines these from
observation.

Why the server returns next_interval_s
--------------------------------------
The cadence is server-negotiated. The client just respects whatever the server
sent. This lets the Optimizer adjust thresholds globally without redeploying
the client. Phase 1C ships the fixed curve; the Optimizer hooks into the same
endpoint in Phase 3.1 and adjusts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import activity, db, diary_writer

logger = logging.getLogger("mempalace.continuous_capture.heartbeat")

# Dead-thread detector cadence
DEAD_DETECT_INTERVAL_S = int(os.environ.get("MEMPALACE_DEAD_DETECT_INTERVAL_S", "30"))

# Initial cadence curve (per spec §4.4, D-CC8)
CADENCE_BANDS = (
    # (session_age_threshold_s, interval_s)
    (180, 180),        # 0–3 min  → 3 min
    (15 * 60, 300),    # 3–15 min → 5 min
    (10_000_000, 120), # 15+ min  → 2 min
)


def cadence_for_age(session_age_s: int) -> int:
    """Return the recommended next_interval_s given the session's current age."""
    for threshold, interval in CADENCE_BANDS:
        if session_age_s < threshold:
            return interval
    return CADENCE_BANDS[-1][1]


def _check_bearer(request: Request, expected_token: bytes) -> bool:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return False
    provided = header.removeprefix("Bearer ").strip().encode("utf-8")
    return secrets.compare_digest(provided, expected_token)


def make_heartbeat_route(get_bearer_token):
    """Closure returning the POST handler for /api/mempalace/heartbeat.

    Bearer-protected — uses the same static bearer as /mcp (D-CC7 / spec §7).
    Pulses do not need a separate token; the bearer already identifies the
    session sufficiently.
    """

    async def heartbeat(request: Request) -> JSONResponse:
        expected_token = get_bearer_token().encode("utf-8")
        if not _check_bearer(request, expected_token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        try:
            payload = await request.json()
        except ValueError:
            return JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"error": "body_not_object"}, status_code=400)

        token_hash = payload.get("token_hash")
        thread_id = payload.get("thread_id")
        last_message_id = payload.get("last_message_id")
        user_state = payload.get("user_state", "active")

        if not token_hash or not isinstance(token_hash, str):
            return JSONResponse({"error": "missing_token_hash"}, status_code=400)
        if user_state not in {"active", "typing", "idle"}:
            user_state = "active"

        # Compute session age. If we have an idle_session row, derive from
        # first_activity_at; otherwise assume 0 (this is the first pulse).
        sess = activity.get_session(token_hash)
        session_age_s = 0
        state_changed = False
        if sess:
            try:
                first = datetime.fromisoformat(sess["first_activity_at"])
                session_age_s = max(0, int((datetime.utcnow() - first).total_seconds()))
            except (KeyError, TypeError, ValueError):
                session_age_s = 0

            # Look up the previous pulse's user_state to compute state_changed
            with db.connect() as conn:
                prev = conn.execute(
                    """
                    SELECT user_state FROM heartbeat
                     WHERE token_hash = ?
                     ORDER BY pulse_at DESC
                     LIMIT 1
                    """,
                    (token_hash,),
                ).fetchone()
                if prev and prev["user_state"] != user_state:
                    state_changed = True

        next_interval = cadence_for_age(session_age_s)

        # Insert the pulse row.
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO heartbeat
                    (token_hash, thread_id, pulse_at, last_message_id,
                     user_state, session_age_at_pulse_s, next_interval_s, state_changed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    thread_id,
                    datetime.utcnow().isoformat(timespec="seconds"),
                    last_message_id,
                    user_state,
                    session_age_s,
                    next_interval,
                    1 if state_changed else 0,
                ),
            )
            conn.commit()

        # Also pulse the activity tracker so the idle sweeper doesn't fire
        # on a heartbeating-but-otherwise-silent session.
        activity.record(
            token_hash,
            method="(heartbeat)",
            thread_id=thread_id,
            last_message_id=last_message_id,
        )

        return JSONResponse(
            {
                "next_interval_s": next_interval,
                "session_age_s": session_age_s,
                "state_changed": state_changed,
            },
            status_code=200,
        )

    return heartbeat


# ── Dead-thread detector ─────────────────────────────────────────────────────


async def _detect_once(proxy: Any, db_path: Path | None = None) -> int:
    """One pass. Returns count of dead-thread diary writes attempted.

    A thread is "dead" if its most recent pulse is older than 2 × the
    next_interval_s that was returned with that pulse, AND the session has
    not already been diary_written.
    """
    now = datetime.utcnow()
    # Threshold for the latest pulse to be considered "recent enough to matter".
    # Look back at most 6 hours — older sessions are stale.
    look_back = (now - timedelta(hours=6)).isoformat(timespec="seconds")

    with db.connect(db_path) as conn:
        # For each token, get the latest pulse and the next_interval it negotiated.
        rows = conn.execute(
            """
            SELECT h.token_hash, h.thread_id, h.last_message_id,
                   MAX(h.pulse_at) AS last_pulse_at,
                   h.next_interval_s
              FROM heartbeat h
             WHERE h.pulse_at > ?
             GROUP BY h.token_hash
            """,
            (look_back,),
        ).fetchall()
        candidates = [dict(r) for r in rows]

    dead = []
    for r in candidates:
        try:
            last_pulse = datetime.fromisoformat(r["last_pulse_at"])
        except (TypeError, ValueError):
            continue
        threshold_s = (r["next_interval_s"] or 180) * 2
        gap_s = (now - last_pulse).total_seconds()
        if gap_s > threshold_s:
            dead.append(r)

    if not dead:
        return 0

    written = 0
    for r in dead:
        token_hash = r["token_hash"]
        # Skip if already written
        sess = activity.get_session(token_hash)
        if sess and sess.get("diary_drawer_id"):
            continue
        session_row = sess or {
            "token_hash": token_hash,
            "first_activity_at": r["last_pulse_at"],
            "last_activity_at": r["last_pulse_at"],
            "thread_id": r.get("thread_id"),
            "last_message_id": r.get("last_message_id"),
            "last_method": "(heartbeat)",
            "activity_count": 0,
        }
        success, drawer_id, err = await diary_writer.write_diary(
            proxy,
            token_hash=token_hash,
            trigger="heartbeat_dead",
            session_row=session_row,
        )
        if success:
            written += 1
            with db.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO diary_write_queue
                        (token_hash, trigger, thread_id, last_message_id,
                         received_at, processed_at, drawer_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        token_hash,
                        "heartbeat_dead",
                        r.get("thread_id"),
                        r.get("last_message_id"),
                        datetime.utcnow().isoformat(timespec="seconds"),
                        datetime.utcnow().isoformat(timespec="seconds"),
                        drawer_id,
                    ),
                )
                if sess:
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
                conn.commit()
        else:
            logger.warning("dead_detector: write failed token_hash=%s... err=%s", token_hash[:8], err)
    return written


async def run_dead_detector(proxy: Any, db_path: Path | None = None) -> None:
    """Long-running dead-thread detector loop."""
    logger.info("dead_detector started: interval=%ds", DEAD_DETECT_INTERVAL_S)
    while True:
        try:
            written = await _detect_once(proxy, db_path=db_path)
            if written:
                logger.info("dead_detector: closed %d dead threads", written)
        except asyncio.CancelledError:
            logger.info("dead_detector: cancelled (graceful shutdown)")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("dead_detector iteration failed: %s", exc)
        try:
            await asyncio.sleep(DEAD_DETECT_INTERVAL_S)
        except asyncio.CancelledError:
            raise
