"""Continuous Capture & Productivity Intelligence — Layer 1 + future Layer 2/3.

version: 0.1.1 (Phase 1A — idle timeout)
spec: docs/deployment/MemPalace_Continuous_Capture_Architecture_v1.0.md
locked decisions: D-CC1..D-CC8 ratified 2026-05-19

Module layout
-------------
  db.py            — SQLite schema (idle_session, diary_write_queue, heartbeat)
  activity.py      — Activity recorder (every MCP call updates last_activity_at)
  diary_writer.py  — AAAK formatter + calls mempalace_diary_write via StdioProxy
  sweeper.py       — Idle sweeper asyncio task (Phase 1A automation)
  routes.py        — Starlette route handlers for /api/mempalace/diary-write

Why a separate module instead of dropping into http_server.py
-------------------------------------------------------------
- http_server.py is the locked wrapper from Phase 2 v0.2; we don't want to
  bloat it. Importing surgically from continuous_capture keeps the wrapper
  diff to ~25 lines.
- Phase 2 v0.2 §A4 forbids second writers to ChromaDB. continuous_capture
  uses the StdioProxy (passed in at startup) to write through the
  established single-writer path.
"""

from __future__ import annotations

__version__ = "0.1.1"  # Phase 1A
