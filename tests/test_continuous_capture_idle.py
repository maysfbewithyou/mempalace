"""Phase 1A Light Test — continuous capture idle-timeout path.

version: 0.1.1
spec: docs/deployment/MemPalace_Continuous_Capture_Architecture_v1.0.md §4.2

Covers
------
- db.init_db creates the schema and is idempotent
- activity.record inserts on first call and upserts on subsequent calls
- diary_writer.format_aaak_entry produces deterministic, well-formed entries
- sweeper._sweep_once picks up idle sessions and writes diary via the proxy
- sweeper is idempotent — already-written sessions are skipped
- audit row appears in diary_write_queue on success
- failure path increments retry_count and captures last_error

Does NOT cover
--------------
- The Starlette route handler (routes.py). That's exercised by
  test_continuous_capture_routes.py once we have TestClient set up
  with the new internal-token auth gating.
- Concurrent activity races between MCP traffic and the sweeper. Phase 2
  v0.2 §A4 (single uvicorn worker) means this is impossible in production,
  but we may add a thread-safety test in Phase 1B regardless.
"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
import tempfile

import pytest


@pytest.fixture
def cc_db(monkeypatch, tmp_path):
    """Isolated continuous_capture.db for each test."""
    db_path = tmp_path / "continuous_capture.db"
    monkeypatch.setenv("MEMPALACE_CC_DB_PATH", str(db_path))
    from mempalace.continuous_capture import db as _db
    _db.init_db()
    return db_path


class _MockProxy:
    """Fake StdioProxy that returns success or failure responses."""

    def __init__(self, *, fail: bool = False, drawer_id: str = "diary_wing_claude_test_xxxxx"):
        self.fail = fail
        self.drawer_id = drawer_id
        self.calls: list[dict] = []

    async def request(self, payload):
        self.calls.append(payload)
        if self.fail:
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "error": {"code": -32603, "message": "mock failure for test"},
            }
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"success": true, "entry_id": "' + self.drawer_id + '"}',
                    }
                ]
            },
        }


def _make_idle(db_path: pathlib.Path, token_hash: str) -> None:
    """Backdate the session's last_activity_at so the sweeper picks it up."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE idle_session SET last_activity_at = ? WHERE token_hash = ?",
            ("2026-01-01T00:00:00", token_hash),
        )
        conn.commit()
    finally:
        conn.close()


# ── db.py ────────────────────────────────────────────────────────────────────


def test_schema_init_idempotent(cc_db):
    """init_db should be safe to call repeatedly without raising or duplicating rows."""
    from mempalace.continuous_capture import db as _db

    assert _db.schema_version() == 1
    _db.init_db()
    _db.init_db()
    assert _db.schema_version() == 1  # still 1, not 2 or more


def test_schema_tables_exist(cc_db):
    """All three tables (idle_session, diary_write_queue, heartbeat) should be present."""
    conn = sqlite3.connect(str(cc_db))
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert {"idle_session", "diary_write_queue", "heartbeat"} <= names


# ── activity.py ──────────────────────────────────────────────────────────────


def test_activity_record_insert_then_upsert(cc_db):
    """First record() inserts, subsequent calls increment activity_count."""
    from mempalace.continuous_capture import activity

    th = activity.hash_token("test_token_at_least_sixteen_chars")
    activity.record(th, method="tools/list")
    sess1 = activity.get_session(th)
    assert sess1 is not None
    assert sess1["activity_count"] == 1
    assert sess1["last_method"] == "tools/list"
    assert sess1["status"] == "active"

    activity.record(th, method="tools/call", thread_id="th-1", last_message_id="m-1")
    sess2 = activity.get_session(th)
    assert sess2["activity_count"] == 2
    assert sess2["last_method"] == "tools/call"
    assert sess2["thread_id"] == "th-1"
    assert sess2["last_message_id"] == "m-1"


def test_activity_hash_is_stable(cc_db):
    """hash_token must be deterministic for the same input."""
    from mempalace.continuous_capture import activity

    assert activity.hash_token("abc") == activity.hash_token("abc")
    assert activity.hash_token("abc") != activity.hash_token("abd")


# ── diary_writer.py ──────────────────────────────────────────────────────────


def test_aaak_format_deterministic():
    from mempalace.continuous_capture import diary_writer

    row = {
        "first_activity_at": "2026-05-19T10:00:00",
        "last_activity_at": "2026-05-19T10:23:00",
        "activity_count": 7,
        "last_method": "tools/call",
    }
    entry = diary_writer.format_aaak_entry(trigger="idle_10min", session_row=row)
    assert entry.startswith("SESSION:2026-05-19|auto.captured.session.end|")
    assert "trigger:idle_10min" in entry
    assert "duration_min:23" in entry
    assert "activity_count:7" in entry
    assert "last_method:tools/call" in entry
    assert entry.endswith("|★★")


def test_aaak_format_handles_unparseable_timestamps():
    """Missing/garbage timestamps degrade to duration:unknown, don't crash."""
    from mempalace.continuous_capture import diary_writer

    entry = diary_writer.format_aaak_entry(
        trigger="manual",
        session_row={
            "first_activity_at": None,
            "last_activity_at": "garbage",
            "activity_count": 0,
            "last_method": None,
        },
    )
    assert "duration:unknown" in entry
    assert "last_method:(none)" in entry


# ── sweeper.py — happy path ──────────────────────────────────────────────────


def test_sweeper_writes_diary_on_idle(cc_db):
    """Idle session triggers a diary write through the mock proxy."""
    from mempalace.continuous_capture import activity, sweeper

    th = activity.hash_token("test_token_at_least_sixteen_chars")
    activity.record(th, method="tools/list")
    _make_idle(cc_db, th)

    mp = _MockProxy()
    attempted = asyncio.run(sweeper._sweep_once(mp))
    assert attempted == 1
    assert len(mp.calls) == 1

    sess = activity.get_session(th)
    assert sess["status"] == "diary_written"
    assert sess["diary_drawer_id"] == "diary_wing_claude_test_xxxxx"


def test_sweeper_is_idempotent(cc_db):
    """A second sweep finds no active idle sessions because the first one closed them."""
    from mempalace.continuous_capture import activity, sweeper

    th = activity.hash_token("test_token_at_least_sixteen_chars")
    activity.record(th, method="tools/list")
    _make_idle(cc_db, th)

    mp = _MockProxy()
    asyncio.run(sweeper._sweep_once(mp))
    second = asyncio.run(sweeper._sweep_once(mp))
    assert second == 0


def test_sweeper_logs_audit_to_queue(cc_db):
    """On success, an audit row appears in diary_write_queue."""
    from mempalace.continuous_capture import activity, sweeper

    th = activity.hash_token("test_token_at_least_sixteen_chars")
    activity.record(th, method="tools/call", thread_id="th-q")
    _make_idle(cc_db, th)

    mp = _MockProxy(drawer_id="diary_wing_claude_audit_test")
    asyncio.run(sweeper._sweep_once(mp))

    conn = sqlite3.connect(str(cc_db))
    try:
        rows = conn.execute(
            "SELECT trigger, drawer_id, thread_id FROM diary_write_queue WHERE token_hash = ?",
            (th,),
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("idle_10min", "diary_wing_claude_audit_test", "th-q")]


# ── sweeper.py — failure path ────────────────────────────────────────────────


def test_sweeper_failure_increments_retry(cc_db):
    """A failed proxy call increments retry_count and captures last_error."""
    from mempalace.continuous_capture import activity, sweeper

    th = activity.hash_token("failing_session_sixteen_plus_chars")
    activity.record(th, method="tools/list")
    _make_idle(cc_db, th)

    fp = _MockProxy(fail=True)
    asyncio.run(sweeper._sweep_once(fp))
    sess = activity.get_session(th)
    assert sess["retry_count"] == 1
    assert sess["status"] == "active"  # still retryable
    assert "mock failure" in (sess["last_error"] or "")


def test_sweeper_marks_failed_after_max_retries(cc_db, monkeypatch):
    """After MAX_RETRIES failures, status becomes 'failed' and sweeper stops picking it up."""
    from mempalace.continuous_capture import activity, sweeper

    # Lower the cap so the test runs quickly
    monkeypatch.setattr(sweeper, "MAX_RETRIES", 2)

    th = activity.hash_token("failing_session_sixteen_plus_chars")
    activity.record(th, method="tools/list")
    _make_idle(cc_db, th)

    fp = _MockProxy(fail=True)
    asyncio.run(sweeper._sweep_once(fp))
    sess = activity.get_session(th)
    assert sess["retry_count"] == 1 and sess["status"] == "active"

    # Re-backdate so the sweeper still picks it up (it was just touched)
    _make_idle(cc_db, th)
    asyncio.run(sweeper._sweep_once(fp))
    sess = activity.get_session(th)
    assert sess["retry_count"] == 2 and sess["status"] == "failed"

    # Now even a re-backdate shouldn't pick it up (retry_count >= MAX_RETRIES,
    # and the SELECT in _sweep_once filters on retry_count < MAX_RETRIES).
    _make_idle(cc_db, th)
    third = asyncio.run(sweeper._sweep_once(fp))
    assert third == 0
