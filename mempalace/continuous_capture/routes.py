"""Starlette route handlers for /api/mempalace/* — Phase 1A.

version: 0.1.1 — Phase 1A
spec ref: MemPalace_Continuous_Capture_Architecture_v1.0.md §4.2, §7

Routes added in this phase:
    POST /api/mempalace/diary-write   — internal-token-gated; idempotent diary write

Routes added in later phases (deliberately not implemented yet):
    POST /api/mempalace/beacon        — Phase 1B (no auth, sendBeacon target)
    POST /api/mempalace/heartbeat     — Phase 1C (bearer auth, pulse + interval negotiation)

Auth model (D-CC7 ratified):
    - /api/mempalace/diary-write trusts MEMPALACE_INTERNAL_API_TOKEN env var.
      This endpoint is meant to be called by the in-container sweeper, the
      beacon worker, and the dead-thread detector. It is also reachable by
      external operators for diagnostic / manual diary writes — same token.
    - Per Phase 2 v0.2 §A6, the BearerAuthMiddleware on /mcp does not gate
      these /api/mempalace/* routes. They have their own auth.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from . import activity, db, diary_writer

logger = logging.getLogger("mempalace.continuous_capture.routes")

INTERNAL_TOKEN_ENV = "MEMPALACE_INTERNAL_API_TOKEN"


def _get_internal_token() -> bytes:
    """Required env var. Endpoint refuses to operate if unset."""
    token = os.environ.get(INTERNAL_TOKEN_ENV)
    if not token or len(token) < 16:
        raise RuntimeError(
            f"{INTERNAL_TOKEN_ENV} env var is required (>= 16 chars). "
            "Generate via: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    return token.encode("utf-8")


def _check_internal_auth(request: Request) -> JSONResponse | None:
    """Return None on success, a JSONResponse on auth failure."""
    expected = _get_internal_token()
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return JSONResponse({"error": "missing_bearer"}, status_code=401)
    provided = header.removeprefix("Bearer ").strip().encode("utf-8")
    if not secrets.compare_digest(provided, expected):
        return JSONResponse({"error": "invalid_internal_token"}, status_code=401)
    return None


def make_diary_write_route(proxy_provider):
    """Closure that returns the diary-write route handler.

    We accept proxy_provider (a callable returning the StdioProxy) rather than
    the proxy itself because the proxy is created in lifespan startup, after
    the routes table is built.
    """

    async def diary_write(request: Request) -> JSONResponse:
        # Auth
        auth_fail = _check_internal_auth(request)
        if auth_fail is not None:
            return auth_fail

        # Parse body
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"error": "invalid_json"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body_not_object"}, status_code=400)

        token_hash = body.get("token_hash")
        trigger = body.get("trigger", "manual")
        if not token_hash or not isinstance(token_hash, str):
            return JSONResponse({"error": "missing_token_hash"}, status_code=400)
        if trigger not in {"idle_10min", "beforeunload", "heartbeat_dead", "manual"}:
            return JSONResponse({"error": f"invalid_trigger:{trigger}"}, status_code=400)

        # Idempotency: if this session already has a diary_drawer_id, return 409.
        session_row = activity.get_session(token_hash)
        if session_row and session_row.get("diary_drawer_id"):
            return JSONResponse(
                {
                    "already_written": True,
                    "drawer_id": session_row["diary_drawer_id"],
                    "trigger_handled": session_row.get("status", "diary_written"),
                },
                status_code=409,
            )

        # If we have no session row yet, build a minimal one (e.g. manual trigger
        # for a token we haven't seen activity from). This lets external callers
        # force-close a session without first pulsing.
        if session_row is None:
            now_iso = datetime.utcnow().isoformat(timespec="seconds")
            session_row = {
                "token_hash": token_hash,
                "first_activity_at": body.get("first_activity_at", now_iso),
                "last_activity_at": body.get("last_activity_at", now_iso),
                "thread_id": body.get("thread_id"),
                "last_message_id": body.get("last_message_id"),
                "last_method": "(none-manual)",
                "activity_count": 0,
            }

        # Synchronous write through the proxy (Phase 1A — async queue is Phase 1B)
        proxy = proxy_provider()
        success, drawer_id, err = await diary_writer.write_diary(
            proxy,
            token_hash=token_hash,
            trigger=trigger,
            session_row=session_row,
        )

        # Update idle_session row to reflect outcome.
        with db.connect() as conn:
            if success:
                conn.execute(
                    """
                    INSERT INTO idle_session (
                        token_hash, first_activity_at, last_activity_at, thread_id,
                        last_message_id, last_method, activity_count, status,
                        diary_written_at, diary_drawer_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'diary_written', ?, ?, ?, ?)
                    ON CONFLICT(token_hash) DO UPDATE SET
                        status           = 'diary_written',
                        diary_written_at = excluded.diary_written_at,
                        diary_drawer_id  = excluded.diary_drawer_id,
                        updated_at       = excluded.updated_at
                    """,
                    (
                        token_hash,
                        session_row["first_activity_at"],
                        session_row["last_activity_at"],
                        session_row.get("thread_id"),
                        session_row.get("last_message_id"),
                        session_row.get("last_method"),
                        session_row.get("activity_count", 0),
                        datetime.utcnow().isoformat(timespec="seconds"),
                        drawer_id,
                        datetime.utcnow().isoformat(timespec="seconds"),
                        datetime.utcnow().isoformat(timespec="seconds"),
                    ),
                )
                conn.commit()
                return JSONResponse(
                    {
                        "ok": True,
                        "drawer_id": drawer_id,
                        "trigger_handled": trigger,
                    },
                    status_code=200,
                )
            # Failure: log to queue for retry, return 5xx
            conn.execute(
                """
                INSERT INTO diary_write_queue (token_hash, trigger, thread_id,
                    last_message_id, received_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    trigger,
                    session_row.get("thread_id"),
                    session_row.get("last_message_id"),
                    datetime.utcnow().isoformat(timespec="seconds"),
                    (err or "unknown")[:500],
                ),
            )
            conn.commit()
        return JSONResponse(
            {"ok": False, "error": err or "unknown", "queued": True},
            status_code=502,
        )

    return diary_write
