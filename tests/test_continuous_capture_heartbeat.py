"""Phase 1C Light Test — heartbeat pulse + dead-thread detector.

version: 0.1.3
spec: docs/deployment/MemPalace_Continuous_Capture_Architecture_v1.0.md §4.4
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def cc_db(monkeypatch, tmp_path):
    db_path = tmp_path / "continuous_capture.db"
    monkeypatch.setenv("MEMPALACE_CC_DB_PATH", str(db_path))
    from mempalace.continuous_capture import db as _db
    _db.init_db()
    return db_path


class _MockProxy:
    def __init__(self, *, fail: bool = False, drawer_id: str = "diary_wing_claude_hb_xxxxx"):
        self.fail = fail
        self.drawer_id = drawer_id
        self.calls = []

    async def request(self, payload):
        self.calls.append(payload)
        if self.fail:
            return {"jsonrpc": "2.0", "id": payload["id"], "error": {"code": -1, "message": "mock"}}
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps({"success": True, "entry_id": self.drawer_id})}
                ]
            },
        }


# ── Cadence curve ────────────────────────────────────────────────────────────


def test_cadence_for_age_brand_new_session():
    """0-3 min → 180s per D-CC8."""
    from mempalace.continuous_capture import heartbeat
    assert heartbeat.cadence_for_age(0) == 180
    assert heartbeat.cadence_for_age(60) == 180
    assert heartbeat.cadence_for_age(179) == 180


def test_cadence_for_age_mid_session():
    """3-15 min → 300s."""
    from mempalace.continuous_capture import heartbeat
    assert heartbeat.cadence_for_age(180) == 300
    assert heartbeat.cadence_for_age(10 * 60) == 300
    assert heartbeat.cadence_for_age(15 * 60 - 1) == 300


def test_cadence_for_age_long_session():
    """15+ min → 120s (kickoff hypothesis: long sessions have more state to lose)."""
    from mempalace.continuous_capture import heartbeat
    assert heartbeat.cadence_for_age(15 * 60) == 120
    assert heartbeat.cadence_for_age(60 * 60) == 120
    assert heartbeat.cadence_for_age(24 * 3600) == 120


# ── Route handler: pulse ─────────────────────────────────────────────────────


def _heartbeat_request(token_hash, *, user_state="active", bearer="test_token_at_least_sixteen_chars"):
    """Make a heartbeat Request-mock with bearer auth."""
    class _Req:
        headers = {"authorization": f"Bearer {bearer}"}
        async def json(self):
            return {
                "token_hash": token_hash,
                "thread_id": "th-hb",
                "last_message_id": "m-hb",
                "user_state": user_state,
            }
    return _Req()


def test_heartbeat_inserts_pulse_row(cc_db):
    from mempalace.continuous_capture import heartbeat

    handler = heartbeat.make_heartbeat_route(lambda: "test_token_at_least_sixteen_chars")
    resp = asyncio.run(handler(_heartbeat_request("0" * 64)))
    assert resp.status_code == 200

    conn = sqlite3.connect(str(cc_db))
    try:
        row = conn.execute(
            "SELECT user_state, thread_id, next_interval_s FROM heartbeat WHERE token_hash = ?",
            ("0" * 64,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "active"
    assert row[1] == "th-hb"
    assert row[2] == 180  # brand-new session → 180s


def test_heartbeat_rejects_bad_bearer(cc_db):
    from mempalace.continuous_capture import heartbeat

    handler = heartbeat.make_heartbeat_route(lambda: "good_token_sixteen_plus_chars_x")

    class _Req:
        headers = {"authorization": "Bearer wrong"}
        async def json(self):
            return {"token_hash": "0" * 64}

    resp = asyncio.run(handler(_Req()))
    assert resp.status_code == 401


def test_heartbeat_state_change_detection(cc_db):
    """Pulsing with user_state different from previous pulse sets state_changed=True."""
    from mempalace.continuous_capture import heartbeat

    handler = heartbeat.make_heartbeat_route(lambda: "test_token_at_least_sixteen_chars")
    th = "1" * 64
    asyncio.run(handler(_heartbeat_request(th, user_state="active")))
    asyncio.run(handler(_heartbeat_request(th, user_state="idle")))

    conn = sqlite3.connect(str(cc_db))
    try:
        rows = conn.execute(
            "SELECT state_changed FROM heartbeat WHERE token_hash = ? ORDER BY pulse_at",
            (th,),
        ).fetchall()
    finally:
        conn.close()
    # First pulse: no prior, state_changed=False. Second: state changed active->idle.
    assert [r[0] for r in rows] == [0, 1]


def test_heartbeat_also_pulses_activity_tracker(cc_db):
    """A heartbeat must keep idle_session.last_activity_at fresh so the sweeper
    doesn't fire on a heartbeating-but-otherwise-silent session."""
    from mempalace.continuous_capture import activity, heartbeat

    handler = heartbeat.make_heartbeat_route(lambda: "test_token_at_least_sixteen_chars")
    th = "2" * 64
    asyncio.run(handler(_heartbeat_request(th)))

    sess = activity.get_session(th)
    assert sess is not None
    assert sess["last_method"] == "(heartbeat)"
    assert sess["status"] == "active"


# ── Dead-thread detector ─────────────────────────────────────────────────────


def _backdate_pulse(db_path, token_hash, *, seconds_ago, next_interval_s=180):
    pulse_at = (datetime.utcnow() - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """INSERT INTO heartbeat
               (token_hash, thread_id, pulse_at, last_message_id, user_state,
                session_age_at_pulse_s, next_interval_s, state_changed)
               VALUES (?, ?, ?, NULL, 'active', 0, ?, 0)""",
            (token_hash, "th-dead", pulse_at, next_interval_s),
        )
        conn.commit()
    finally:
        conn.close()


def test_detector_finds_dead_thread(cc_db):
    """A pulse > 2× next_interval_s in the past triggers a diary write."""
    from mempalace.continuous_capture import activity, heartbeat

    th = activity.hash_token("dead_thread_test_sixteen_plus_chr")
    activity.record(th, method="tools/list")
    # Last pulse was 400s ago, with next_interval_s=180 → 2x = 360 < 400. Dead.
    _backdate_pulse(cc_db, th, seconds_ago=400, next_interval_s=180)

    proxy = _MockProxy(drawer_id="diary_wing_claude_dead")
    written = asyncio.run(heartbeat._detect_once(proxy))
    assert written == 1
    assert len(proxy.calls) == 1

    sess = activity.get_session(th)
    assert sess["status"] == "diary_written"
    assert sess["diary_drawer_id"] == "diary_wing_claude_dead"


def test_detector_skips_recent_pulses(cc_db):
    """A pulse less than 2× next_interval_s ago is still considered alive."""
    from mempalace.continuous_capture import activity, heartbeat

    th = activity.hash_token("alive_thread_test_sixteen_plus_ch")
    activity.record(th, method="tools/list")
    # Last pulse 100s ago, next_interval_s=180 → 2x = 360 > 100. Alive.
    _backdate_pulse(cc_db, th, seconds_ago=100, next_interval_s=180)

    proxy = _MockProxy()
    written = asyncio.run(heartbeat._detect_once(proxy))
    assert written == 0
    assert len(proxy.calls) == 0


def test_detector_skips_already_written(cc_db):
    """A dead thread that has already been diary_written is not re-written."""
    from mempalace.continuous_capture import activity, heartbeat

    th = activity.hash_token("already_written_thread_sixteen_p")
    activity.record(th, method="tools/list")
    conn = sqlite3.connect(str(cc_db))
    try:
        conn.execute(
            "UPDATE idle_session SET status='diary_written', diary_drawer_id='diary_pre' WHERE token_hash = ?",
            (th,),
        )
        conn.commit()
    finally:
        conn.close()
    _backdate_pulse(cc_db, th, seconds_ago=600, next_interval_s=180)

    proxy = _MockProxy()
    written = asyncio.run(heartbeat._detect_once(proxy))
    assert written == 0
    assert len(proxy.calls) == 0


def test_detector_logs_audit_to_queue(cc_db):
    """A dead-detector close also appends an audit row in diary_write_queue."""
    from mempalace.continuous_capture import activity, heartbeat

    th = activity.hash_token("dead_audit_test_sixteen_plus_chr_")
    activity.record(th, method="tools/list")
    _backdate_pulse(cc_db, th, seconds_ago=600, next_interval_s=180)

    proxy = _MockProxy(drawer_id="diary_wing_claude_dead_audit")
    asyncio.run(heartbeat._detect_once(proxy))

    conn = sqlite3.connect(str(cc_db))
    try:
        rows = conn.execute(
            "SELECT trigger, drawer_id FROM diary_write_queue WHERE token_hash = ?",
            (th,),
        ).fetchall()
    finally:
        conn.close()
    assert rows == [("heartbeat_dead", "diary_wing_claude_dead_audit")]
