"""AAAK diary writer — formats an idle-closed session entry and calls
mempalace_diary_write via the StdioProxy.

version: 0.1.1 — Phase 1A
spec ref: MemPalace_Continuous_Capture_Architecture_v1.0.md §4.2, §8

Phase 1A simplification: we do NOT fetch the full message context from the
Anthropic API in Phase 1A. The placeholder AAAK entry captures the deterministic
facts we already have (timestamps, activity count, last MCP method). Phase 1B's
beacon worker will refine entries by enriching with message context when
ANTHROPIC_API_KEY is configured — see TCL D-CC3.

Why call through the StdioProxy: Phase 2 v0.2 §A4 (single-writer ChromaDB).
The wrapper subprocess is the sole writer; this module must use the JSON-RPC
roundtrip, not an in-process import of mempalace.mcp_server.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger("mempalace.continuous_capture.diary_writer")

DEFAULT_AGENT_NAME = "Claude"  # matches Recovery-Pass-v1.0 convention (wing_claude)
DEFAULT_TOPIC = "session-end"


def format_aaak_entry(
    *,
    trigger: str,
    session_row: dict,
    extra_context: str | None = None,
) -> str:
    """Format an AAAK-compressed diary entry from an idle_session row.

    Format conventions (mempalace.dialect for the full spec):
        SESSION:<YYYY-MM-DD>|<one-line-fact>|trigger:<source>|<metric>:<value>|★

    Phase 1A entries are deterministic — no message-context narrative. Just the
    facts of how the session ended. This gives the Pattern Analyst (Phase 3.2)
    structured data to cluster on even before Phase 1B enrichment lands.
    """
    first = session_row.get("first_activity_at", "?")
    last = session_row.get("last_activity_at", "?")
    activity_count = session_row.get("activity_count", 0)
    last_method = session_row.get("last_method") or "(none)"

    # Compute session duration in minutes if we can parse both timestamps.
    duration_min: int | None
    try:
        t_first = datetime.fromisoformat(first)
        t_last = datetime.fromisoformat(last)
        duration_min = max(0, int((t_last - t_first).total_seconds() / 60))
    except (ValueError, TypeError):
        duration_min = None

    date_part = (first or "?")[:10]
    duration_str = f"duration_min:{duration_min}" if duration_min is not None else "duration:unknown"

    parts = [
        f"SESSION:{date_part}",
        "auto.captured.session.end",
        f"trigger:{trigger}",
        duration_str,
        f"activity_count:{activity_count}",
        f"last_method:{last_method}",
    ]
    if extra_context:
        parts.append(extra_context)
    # Phase 1A confidence: medium — facts are reliable, narrative is absent.
    parts.append("★★")

    return "|".join(parts)


async def write_diary(
    proxy: Any,           # StdioProxy — typed Any to avoid circular import
    *,
    token_hash: str,
    trigger: str,
    session_row: dict,
    agent_name: str = DEFAULT_AGENT_NAME,
    topic: str = DEFAULT_TOPIC,
) -> tuple[bool, str | None, str | None]:
    """Write one diary entry via the StdioProxy.

    Returns (success, drawer_id, error_message). On failure, the caller is
    responsible for retry/queue logic; this function does not retry itself.

    Why not retry here: retry policy lives in the sweeper / beacon worker, where
    we have access to retry_count and exponential-backoff state. This function
    is a single-shot operation by design.
    """
    entry = format_aaak_entry(trigger=trigger, session_row=session_row)

    request_id = f"diary-write-{uuid.uuid4().hex[:12]}"
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": "mempalace_diary_write",
            "arguments": {
                "agent_name": agent_name,
                "entry": entry,
                "topic": topic,
            },
        },
    }

    try:
        resp = await proxy.request(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("diary write proxy call failed: %s", exc)
        return False, None, f"proxy_error: {exc!s}"

    if not isinstance(resp, dict):
        return False, None, f"unexpected_response_type: {type(resp).__name__}"
    if "error" in resp:
        err = resp["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return False, None, f"jsonrpc_error: {msg}"

    # Extract drawer_id from the tool response. mempalace_diary_write returns
    # a dict with success + entry_id (see mcp_server.py:812-855). MCP wraps
    # tool results in {"result": {"content": [{"type": "text", "text": "{...}"}]}}
    # or similar — be defensive in parsing.
    drawer_id = _extract_drawer_id(resp)
    if not drawer_id:
        logger.warning(
            "diary write succeeded but no drawer_id parseable from response: %r",
            resp,
        )
    logger.info(
        "diary write ok token_hash=%s... trigger=%s drawer_id=%s",
        token_hash[:8], trigger, drawer_id or "(unparsed)",
    )
    return True, drawer_id, None


def _extract_drawer_id(resp: dict) -> str | None:
    """Best-effort drawer_id extraction from the tool result.

    mempalace_diary_write's handler returns:
        {"success": True, "entry_id": "diary_wing_claude_..."}

    MCP wraps that in:
        {"jsonrpc":"2.0","id":...,"result":{"content":[{"type":"text","text":"<json>"}]}}

    We dig through both shapes; if the format ever changes upstream we fall
    back to None and log (caller is non-fatal on unparsed).
    """
    result = resp.get("result")
    if not isinstance(result, dict):
        return None
    # Direct shape (some MCP impls)
    if "entry_id" in result:
        return str(result["entry_id"])
    # Content-wrapped shape (typical FastMCP / official SDK)
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if not isinstance(first, dict):
        return None
    text = first.get("text")
    if not isinstance(text, str):
        return None
    try:
        import json
        data = json.loads(text)
        return data.get("entry_id") if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None
