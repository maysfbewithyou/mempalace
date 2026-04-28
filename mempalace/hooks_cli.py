"""
Hook logic for MemPalace — Python implementation of session-start, stop, and precompact hooks.

Reads JSON from stdin, outputs JSON to stdout.
Supported hooks: session-start, stop, precompact
Supported harnesses: claude-code, codex (extensible to cursor, gemini, etc.)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SAVE_INTERVAL = 15
STATE_DIR = Path.home() / ".mempalace" / "hook_state"
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB before rotation
MAX_LOG_BACKUPS = 3


def _atomic_write(filepath: Path, content: str):
    """Write content to a file atomically using a temp file + rename.

    This prevents TOCTOU race conditions where concurrent hook invocations
    could read a partially-written state file. The os.rename() call is
    atomic on POSIX filesystems when source and destination are on the same
    filesystem (which they are, since we use the same directory).
    """
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(filepath.parent), prefix=".tmp_")
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_path, str(filepath))  # Atomic on POSIX; safe on Windows
        try:
            filepath.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
    except OSError:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except (OSError, UnboundLocalError):
            pass

STOP_BLOCK_REASON = (
    "AUTO-SAVE checkpoint. Save key topics, decisions, and details from this "
    "session to your memory system. Focus on: venue decisions, vendor updates, "
    "timeline changes, budget approvals, client preferences, equipment specs, "
    "and production notes. Organize into appropriate wings and rooms. Use "
    "verbatim quotes where possible. Continue conversation after saving."
)

PRECOMPACT_BLOCK_REASON = (
    "COMPACTION IMMINENT. Save ALL event details, vendor agreements, venue "
    "specs, timeline milestones, budget figures, client requests, equipment "
    "notes, and production decisions from this session to your memory system. "
    "Be thorough \u2014 after compaction, detailed context will be lost. "
    "Organize into appropriate wings and rooms. Use verbatim quotes where "
    "possible. Save everything, then allow compaction to proceed."
)


def _sanitize_session_id(session_id: str) -> str:
    """Only allow alnum, dash, underscore to prevent path traversal."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)
    return sanitized or "unknown"


def _count_human_messages(transcript_path: str) -> int:
    """Count human messages in a JSONL transcript, skipping command-messages."""
    path = Path(transcript_path).expanduser()
    if not path.is_file():
        return 0
    count = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    msg = entry.get("message", {})
                    if isinstance(msg, dict) and msg.get("role") == "user":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            if "<command-message>" in content:
                                continue
                        elif isinstance(content, list):
                            text = " ".join(
                                b.get("text", "") for b in content if isinstance(b, dict)
                            )
                            if "<command-message>" in text:
                                continue
                        count += 1
                except (json.JSONDecodeError, AttributeError):
                    pass
    except OSError:
        return 0
    return count


def _rotate_log(log_path: Path):
    """Rotate log file if it exceeds MAX_LOG_SIZE. Keeps MAX_LOG_BACKUPS copies."""
    try:
        if log_path.is_file() and log_path.stat().st_size > MAX_LOG_SIZE:
            for i in range(MAX_LOG_BACKUPS - 1, 0, -1):
                src = log_path.with_suffix(f".log.{i}")
                dst = log_path.with_suffix(f".log.{i + 1}")
                if src.is_file():
                    src.rename(dst)
            log_path.rename(log_path.with_suffix(f".log.1"))
    except OSError:
        pass


def _ensure_state_dir():
    """Create state directory with restrictive permissions."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_DIR.chmod(0o700)
    except (OSError, NotImplementedError):
        pass


def _log(message: str):
    """Append to hook state log file with automatic rotation."""
    try:
        _ensure_state_dir()
        log_path = STATE_DIR / "hook.log"
        _rotate_log(log_path)
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
        try:
            log_path.chmod(0o600)
        except (OSError, NotImplementedError):
            pass
    except OSError:
        pass


def _output(data: dict):
    """Print JSON to stdout with consistent formatting (pretty-printed)."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _validate_mempal_dir(mempal_dir: str) -> bool:
    """Validate MEMPAL_DIR is a real directory under the user's home or a known safe path.

    Prevents an attacker from setting MEMPAL_DIR to an arbitrary location
    like /etc or another user's home to trigger processing of sensitive files.
    """
    if not mempal_dir or not os.path.isdir(mempal_dir):
        return False
    try:
        resolved = os.path.realpath(mempal_dir)
        home = os.path.realpath(str(Path.home()))
        # Only allow paths under user's home directory — no /tmp, no system dirs
        if resolved.startswith(home + os.sep) or resolved == home:
            return True
        _log(f"MEMPAL_DIR rejected: {resolved} is not under {home}")
        return False
    except (OSError, ValueError):
        return False


def _maybe_auto_ingest():
    """If MEMPAL_DIR is set, validated, and exists, run mempalace mine in background."""
    mempal_dir = os.environ.get("MEMPAL_DIR", "")
    if _validate_mempal_dir(mempal_dir):
        try:
            log_path = STATE_DIR / "hook.log"
            with open(log_path, "a") as log_f:
                subprocess.Popen(
                    [sys.executable, "-m", "mempalace", "mine", mempal_dir],
                    stdout=log_f,
                    stderr=log_f,
                )
        except OSError:
            pass


SUPPORTED_HARNESSES = {"claude-code", "codex"}


def _parse_harness_input(data: dict, harness: str) -> dict:
    """Parse stdin JSON according to the harness type."""
    if harness not in SUPPORTED_HARNESSES:
        print(f"Unknown harness: {harness}", file=sys.stderr)
        sys.exit(1)
    return {
        "session_id": _sanitize_session_id(str(data.get("session_id", "unknown"))),
        "stop_hook_active": data.get("stop_hook_active", False),
        "transcript_path": str(data.get("transcript_path", "")),
    }


def hook_stop(data: dict, harness: str):
    """Stop hook: block every N messages for auto-save."""
    parsed = _parse_harness_input(data, harness)
    session_id = parsed["session_id"]
    stop_hook_active = parsed["stop_hook_active"]
    transcript_path = parsed["transcript_path"]

    # If already in a save cycle, let through (infinite-loop prevention)
    if str(stop_hook_active).lower() in ("true", "1", "yes"):
        _output({})
        return

    # Count human messages
    exchange_count = _count_human_messages(transcript_path)

    # Track last save point
    _ensure_state_dir()
    last_save_file = STATE_DIR / f"{session_id}_last_save"
    last_save = 0
    if last_save_file.is_file():
        try:
            last_save = int(last_save_file.read_text().strip())
        except (ValueError, OSError):
            last_save = 0

    since_last = exchange_count - last_save

    _log(f"Session {session_id}: {exchange_count} exchanges, {since_last} since last save")

    if since_last >= SAVE_INTERVAL and exchange_count > 0:
        # Update last save point atomically to prevent TOCTOU races
        _atomic_write(last_save_file, str(exchange_count))

        _log(f"TRIGGERING SAVE at exchange {exchange_count}")

        # Optional: auto-ingest if MEMPAL_DIR is set
        _maybe_auto_ingest()

        _output({"decision": "block", "reason": STOP_BLOCK_REASON})
    else:
        _output({})


def hook_session_start(data: dict, harness: str):
    """Session start hook: initialize session tracking state."""
    parsed = _parse_harness_input(data, harness)
    session_id = parsed["session_id"]

    _log(f"SESSION START for session {session_id}")

    # Initialize session state directory with restrictive permissions
    _ensure_state_dir()

    # Pass through — no blocking on session start
    _output({})


def hook_precompact(data: dict, harness: str):
    """Precompact hook: always block with comprehensive save instruction."""
    parsed = _parse_harness_input(data, harness)
    session_id = parsed["session_id"]

    _log(f"PRE-COMPACT triggered for session {session_id}")

    # Optional: auto-ingest synchronously before compaction (so memories land first)
    mempal_dir = os.environ.get("MEMPAL_DIR", "")
    if _validate_mempal_dir(mempal_dir):
        try:
            log_path = STATE_DIR / "hook.log"
            with open(log_path, "a") as log_f:
                subprocess.run(
                    [sys.executable, "-m", "mempalace", "mine", mempal_dir],
                    stdout=log_f,
                    stderr=log_f,
                    timeout=60,
                )
        except OSError:
            pass

    # Always block -- compaction = save everything
    _output({"decision": "block", "reason": PRECOMPACT_BLOCK_REASON})


def run_hook(hook_name: str, harness: str):
    """Main entry point: read stdin JSON, dispatch to hook handler."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _log("WARNING: Failed to parse stdin JSON, proceeding with empty data")
        data = {}

    hooks = {
        "session-start": hook_session_start,
        "stop": hook_stop,
        "precompact": hook_precompact,
    }

    handler = hooks.get(hook_name)
    if handler is None:
        print(f"Unknown hook: {hook_name}", file=sys.stderr)
        sys.exit(1)

    handler(data, harness)
