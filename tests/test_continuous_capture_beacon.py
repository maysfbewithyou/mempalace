"""Phase 1B Light Test — beacon endpoint + worker.

version: 0.1.2
spec: docs/deployment/MemPalace_Continuous_Capture_Architecture_v1.0.md §4.3

Worker logic exercised via direct calls into beacon._drain_once. The Starlette
route handler is exercised via a minimal request-mock (no httpx dep required).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def cc_db(monkeypatch, tmp_path):
    db_path = tmp_path / "continuous_capture.db"
    monkeypatch.setenv("MEMPALACE_CC_DB_PATH", str(db_path))
    from mempalace.continuous_capture import db as _db
    _db.init_db()
    return db_path


class _MockProxy:
    def __init__(self, *, fail: bool = False, drawer_id: str = "diary_wing_claude_b_xxxxx"):
        self.fail = fail
        self.drawer_id = drawer_id
        self.calls: list[dict] = []

    async def request(self, payload):
        self.calls.append(payload)
        if self.fail:
            return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -1, "message": "mock fail"}}
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps({"success": True, "entry_id": self.drawer_id})}
                ]
            },
        }


def _enqueue(db_path, token_hash, trigger="beforeunload", thread_id=None):
    """Helper — insert directly into diary_write_queue (skips the route)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """INSERT INTO diary_write_queue
               (token_hash, trigger, thread_id, last_message_id, received_at)
               VALUES (?, ?, ?, ?, '2026-05-19T10:00:00')""",
            (token_hash, trigger, thread_id, None),
        )
        conn.commit()
    finally:
        conn.close()


# ── Worker: happy path ──────────────────────────────────────────────────────


def test_worker_drains_unprocessed_queue(cc_db):
    from mempalace.continuous_capture import activity, beacon

    th = activity.hash_token("session_token_sixteen_plus_chars")
    activity.record(th, method="tools/list")
    _enqueue(cc_db, th, trigger="beforeunload")

    proxy = _MockProxy(drawer_id="diary_wing_claude_b_drain")
    n = asyncio.run(beacon._drain_once(proxy))
    assert n == 1
    assert len(proxy.calls) == 1

    conn = sqlite3.connect(str(cc_db))
    try:
        row = conn.execute(
            "SELECT processed_at, drawer_id FROM diary_write_queue WHERE token_hash = ?",
            (th,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] is not None
    assert row[1] == "diary_wing_claude_b_drain"

    # idle_session should also be marked diary_written
    sess = activity.get_session(th)
    assert sess["status"] == "diary_written"
    assert sess["diary_drawer_id"] == "diary_wing_claude_b_drain"


def test_worker_dedup_skips_already_written(cc_db):
    """If idle_session already has a diary_drawer_id (e.g. sweeper got there
    first), the worker marks the queue row processed without calling the proxy."""
    from mempalace.continuous_capture import activity, beacon

    th = activity.hash_token("session_already_written_sixteen_p")
    activity.record(th, method="tools/list")

    # Simulate the sweeper having already written
    conn = sqlite3.connect(str(cc_db))
    try:
        conn.execute(
            """UPDATE idle_session
                  SET status='diary_written', diary_drawer_id='diary_wing_claude_sweeper_already'
                WHERE token_hash = ?""",
            (th,),
        )
        conn.commit()
    finally:
        conn.close()

    _enqueue(cc_db, th, trigger="beforeunload")

    proxy = _MockProxy()
    asyncio.run(beacon._drain_once(proxy))
    assert len(proxy.calls) == 0  # dedup — no proxy call

    conn = sqlite3.connect(str(cc_db))
    try:
        row = conn.execute(
            "SELECT processed_at, drawer_id FROM diary_write_queue WHERE token_hash = ?",
            (th,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] is not None
    assert row[1] == "diary_wing_claude_sweeper_already"


def test_worker_handles_no_activity_history(cc_db):
    """A beacon for a token we've never seen activity for still results in a write,
    using a synthesized session_row."""
    from mempalace.continuous_capture import beacon

    th = "0" * 64  # synthetic hash, never recorded via activity
    _enqueue(cc_db, th, trigger="beforeunload", thread_id="th-only-beacon")

    proxy = _MockProxy(drawer_id="diary_wing_claude_b_synth")
    n = asyncio.run(beacon._drain_once(proxy))
    assert n == 1
    assert len(proxy.calls) == 1


def test_worker_failure_increments_retry(cc_db):
    from mempalace.continuous_capture import activity, beacon

    th = activity.hash_token("failing_b_session_sixteen_plus_ch")
    activity.record(th, method="tools/list")
    _enqueue(cc_db, th, trigger="beforeunload")

    proxy = _MockProxy(fail=True)
    asyncio.run(beacon._drain_once(proxy))

    conn = sqlite3.connect(str(cc_db))
    try:
        row = conn.execute(
            "SELECT retry_count, processed_at, last_error FROM diary_write_queue WHERE token_hash = ?",
            (th,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 1
    assert row[1] is None  # not yet processed
    assert "mock fail" in (row[2] or "")


def test_worker_marks_processed_at_max_retries(cc_db, monkeypatch):
    from mempalace.continuous_capture import activity, beacon

    monkeypatch.setattr(beacon, "BEACON_MAX_RETRIES", 2)

    th = activity.hash_token("failing_b_session_sixteen_plus_ch")
    activity.record(th, method="tools/list")
    _enqueue(cc_db, th, trigger="beforeunload")

    proxy = _MockProxy(fail=True)
    asyncio.run(beacon._drain_once(proxy))
    asyncio.run(beacon._drain_once(proxy))  # retry_count -> 2 hits max

    conn = sqlite3.connect(str(cc_db))
    try:
        row = conn.execute(
            "SELECT retry_count, processed_at FROM diary_write_queue WHERE token_hash = ?",
            (th,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 2
    assert row[1] is not None  # processed (with error) — won't be retried again


# ── Route handler: enqueue ──────────────────────────────────────────────────


def test_beacon_route_enqueues_valid_payload(cc_db):
    """Direct unit test on the route closure — no Starlette TestClient required."""
    from mempalace.continuous_capture import beacon

    handler = beacon.make_beacon_route(lambda: None)

    # Minimal Starlette-Request-shaped mock
    class _Req:
        headers = {}
        async def body(self):
            return json.dumps({
                "token_hash": "abcd1234" * 8,
                "trigger": "beforeunload",
                "thread_id": "th-route",
                "last_message_id": "m-route",
            }).encode("utf-8")

    resp = asyncio.run(handler(_Req()))
    assert resp.status_code == 204

    conn = sqlite3.connect(str(cc_db))
    try:
        row = conn.execute(
            "SELECT trigger, thread_id, last_message_id FROM diary_write_queue WHERE token_hash = ?",
            ("abcd1234" * 8,),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("beforeunload", "th-route", "m-route")


def test_beacon_route_204_on_malformed_payload(cc_db):
    """Malformed payloads still return 204 — beacons are fire-and-forget."""
    from mempalace.continuous_capture import beacon

    handler = beacon.make_beacon_route(lambda: None)

    class _Req:
        headers = {}
        async def body(self):
            return b"this is not json at all"

    resp = asyncio.run(handler(_Req()))
    assert resp.status_code == 204


def test_beacon_route_204_on_missing_token_hash(cc_db):
    from mempalace.continuous_capture import beacon

    handler = beacon.make_beacon_route(lambda: None)

    class _Req:
        headers = {}
        async def body(self):
            return json.dumps({"trigger": "beforeunload"}).encode("utf-8")

    resp = asyncio.run(handler(_Req()))
    assert resp.status_code == 204

    # And nothing got enqueued
    conn = sqlite3.connect(str(cc_db))
    try:
        count = conn.execute("SELECT COUNT(*) FROM diary_write_queue").fetchone()[0]
    finally:
        conn.close()
    assert count == 0
