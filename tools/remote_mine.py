#!/usr/bin/env python3
"""remote_mine.py — Mine local files into a hosted MemPalace via /mcp.

version: 0.1
phase: 4

Walks a local directory, reads each text file, and files one drawer per file
through the hosted MemPalace MCP server's mempalace_add_drawer tool.

Auth: static bearer token (Phase 2 fallback path) or OAuth-issued JWT.
Default reads the static bearer from ~/.mempalace_client/token.

Usage:
  python tools/remote_mine.py \\
      --base-url https://claude-brain.tstly.dev \\
      --wing wing_atlas \\
      --dir "C:/Users/phatt/Documents/GitHub/atlas" \\
      [--limit 5] [--dry-run] [--include-ext .md,.txt]

Routing:
  - --wing is required (one of: wing_mega, wing_iep, wing_atlas, wing_personal).
  - room is derived per file: parent folder name slugified (lowercase, hyphens).
  - source_file is recorded as a relative path from --dir.
  - agent is hardcoded "remote_miner".

Skips:
  - Binary files (detected via null bytes in first 8KB).
  - Files >100KB (truncates content with a marker; consider chunking later).
  - Anything matching --skip-glob patterns (defaults: .git, node_modules,
    __pycache__, .pytest_cache, *.pyc, *.pyo, *.so, *.dylib).

Idempotency:
  This v0.1 does NOT call mempalace_check_duplicate before adding. Re-mining
  the same directory will create duplicate drawers. Use --dry-run first to
  preview. A future v0.2 may add hash-based dedup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib import request as _urllib_request
from urllib.error import HTTPError, URLError


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://claude-brain.tstly.dev"
DEFAULT_TOKEN_FILE = Path.home() / ".mempalace_client" / "token"

DEFAULT_SKIP_DIRS = {
    ".git", ".github", ".venv", "venv", "env",
    "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".next", ".nuxt", ".cache",
    ".idea", ".vscode", ".DS_Store",
}
DEFAULT_SKIP_EXT = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico", ".svg",
    ".mp3", ".mp4", ".mov", ".avi", ".mkv", ".wav", ".flac",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".pdf",  # PDFs need extraction; not handled in v0.1
    ".docx", ".xlsx", ".pptx",  # Office formats; not handled in v0.1
}

MAX_DRAWER_BYTES = 100_000  # 100 KB hard cap per drawer (matches upstream limit)
BINARY_SNIFF_BYTES = 8_192


# ── HTTP helper ───────────────────────────────────────────────────────────────


class MCPClient:
    """Tiny synchronous JSON-RPC over HTTP client for MemPalace."""

    def __init__(self, base_url: str, bearer_token: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token.strip()
        self.timeout = timeout
        self._req_id = 0

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call an MCP tool. Returns the parsed result dict (or raises)."""
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        body = json.dumps(payload).encode("utf-8")
        req = _urllib_request.Request(
            url=f"{self.base_url}/mcp",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.bearer_token}",
                # Cloudflare blocks Python-urllib/* UA with error 1010 (banned
                # browser signature). Use a Mozilla-compatible UA so requests
                # reach the origin.
                "User-Agent": "mempalace-remote-miner/0.1 "
                              "(Mozilla/5.0; +https://github.com/maysfbewithyou/mempalace)",
            },
        )
        try:
            with _urllib_request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
        except HTTPError as exc:
            raise RuntimeError(
                f"HTTP {exc.code} {exc.reason} from {name}: "
                f"{exc.read().decode('utf-8', 'replace')[:400]}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Network error calling {name}: {exc}") from exc

        parsed = json.loads(resp_body)
        if "error" in parsed:
            err = parsed["error"]
            raise RuntimeError(f"MCP error from {name}: {err.get('message', err)}")
        return parsed.get("result", {})


# ── File handling ─────────────────────────────────────────────────────────────


def _is_binary(path: Path) -> bool:
    """Detect binary files by sniffing the first BINARY_SNIFF_BYTES for null bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(BINARY_SNIFF_BYTES)
        return b"\x00" in chunk
    except OSError:
        return True  # unreadable → treat as binary, skip


def _slugify_room(name: str) -> str:
    """Convert a filename or folder name into a hyphenated lowercase slug."""
    base = re.sub(r"[^a-zA-Z0-9_\-\. ]", "", name).strip().lower()
    base = re.sub(r"[\s_\.]+", "-", base)
    base = re.sub(r"-+", "-", base).strip("-")
    return base or "unsorted"


def _read_text_capped(path: Path, limit: int = MAX_DRAWER_BYTES) -> tuple[str, bool]:
    """Read file content as UTF-8, capping at `limit` bytes. Returns (text, was_truncated)."""
    raw = path.read_bytes()
    truncated = False
    if len(raw) > limit:
        raw = raw[:limit]
        truncated = True
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += f"\n\n[...TRUNCATED at {limit} bytes by remote_mine.py — original {path.stat().st_size} bytes]"
    return text, truncated


def _walk_files(root: Path, skip_dirs: set[str], skip_ext: set[str], include_ext: set[str] | None):
    """Yield Path objects for files we should mine."""
    for dirpath, dirnames, filenames in os.walk(root):
        # Mutate dirnames in-place to skip directories
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".pytest_cache")]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() in skip_ext:
                continue
            if include_ext is not None and p.suffix.lower() not in include_ext:
                continue
            yield p


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mine a local directory into hosted MemPalace.")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"MCP server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--token-file", default=str(DEFAULT_TOKEN_FILE),
                   help=f"Path to bearer-token file (default: {DEFAULT_TOKEN_FILE})")
    p.add_argument("--token", default=None,
                   help="Bearer token literal (overrides --token-file)")
    p.add_argument("--wing", required=True,
                   choices=["wing_mega", "wing_iep", "wing_atlas", "wing_personal"],
                   help="Wing to file content under")
    p.add_argument("--dir", required=True, dest="source_dir",
                   help="Source directory to mine")
    p.add_argument("--limit", type=int, default=0,
                   help="Stop after N files (0 = no limit)")
    p.add_argument("--dry-run", action="store_true",
                   help="Walk + classify but don't actually call MCP")
    p.add_argument("--include-ext", default=None,
                   help="Comma-separated extensions to include (e.g. .md,.txt). "
                        "If unset, all non-binary text files are included.")
    p.add_argument("--skip-glob", action="append", default=[],
                   help="Additional directory names to skip (repeatable)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Print every file decision")
    p.add_argument("--rps", type=float, default=0.9,
                   help="Max requests per second (default 0.9 — stays under upstream's 60/min limit)")
    args = p.parse_args(argv)

    # Resolve auth
    if args.token:
        token = args.token.strip()
    else:
        token_path = Path(args.token_file).expanduser()
        if not token_path.exists():
            print(f"ERROR: token file not found: {token_path}", file=sys.stderr)
            return 2
        token = token_path.read_text(encoding="utf-8").strip()

    if not token or len(token) < 16:
        print("ERROR: token is empty or too short", file=sys.stderr)
        return 2

    # Resolve source dir
    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.is_dir():
        print(f"ERROR: --dir is not a directory: {source_dir}", file=sys.stderr)
        return 2

    # Skip patterns
    skip_dirs = set(DEFAULT_SKIP_DIRS) | set(args.skip_glob)
    skip_ext = set(DEFAULT_SKIP_EXT)
    include_ext = None
    if args.include_ext:
        include_ext = {x.strip().lower() for x in args.include_ext.split(",") if x.strip()}

    # Build client
    client = MCPClient(base_url=args.base_url, bearer_token=token)

    # Confirm connectivity
    if not args.dry_run:
        print(f"Probing {args.base_url}/mcp ...")
        try:
            status = client.call_tool("mempalace_status", {})
            inner = json.loads(status["content"][0]["text"])
            print(f"  palace: {inner.get('palace_path')}, "
                  f"current drawers: {inner.get('total_drawers')}")
        except Exception as exc:
            print(f"ERROR: probe failed: {exc}", file=sys.stderr)
            return 3

    # Walk + mine
    print(f"\nWalking {source_dir} (wing={args.wing}, dry_run={args.dry_run})...")
    n_filed = 0
    n_skipped_binary = 0
    n_skipped_ext = 0
    n_truncated = 0
    n_errors = 0
    started = time.time()

    for path in _walk_files(source_dir, skip_dirs, skip_ext, include_ext):
        rel = path.relative_to(source_dir)
        # Files at the top of source_dir → room = source_dir name slugified.
        # Files in subdirectories → room = immediate parent folder name slugified.
        if path.parent == source_dir:
            room = _slugify_room(source_dir.name)
        else:
            room = _slugify_room(path.parent.name)

        if _is_binary(path):
            n_skipped_binary += 1
            if args.verbose:
                print(f"  SKIP binary: {rel}")
            continue

        try:
            content, truncated = _read_text_capped(path)
        except Exception as exc:
            n_errors += 1
            print(f"  READ ERROR: {rel}: {exc}")
            continue

        if truncated:
            n_truncated += 1

        if args.dry_run:
            print(f"  [dry] {rel} -> wing={args.wing} room={room} "
                  f"({len(content)} chars{' truncated' if truncated else ''})")
            n_filed += 1
        else:
            # Rate-limit throttle. Upstream's RateLimiter is 60 req/min hardcoded.
            # We aim for --rps below 1.0 to stay safely under.
            if args.rps and args.rps > 0:
                min_interval = 1.0 / args.rps
                elapsed_since_start = time.time() - started
                expected = n_filed * min_interval
                if elapsed_since_start < expected:
                    time.sleep(expected - elapsed_since_start)

            try:
                client.call_tool("mempalace_add_drawer", {
                    "wing": args.wing,
                    "room": room,
                    "content": content,
                    "source_file": str(rel),
                })
                if args.verbose:
                    print(f"  filed: {rel} -> {args.wing}/{room}")
                n_filed += 1
            except Exception as exc:
                n_errors += 1
                print(f"  ADD ERROR: {rel}: {exc}")
                # Count failed attempts toward limit too — otherwise a pathological
                # error case would walk the entire tree.
                if args.limit and (n_filed + n_errors) >= args.limit * 5:
                    print(f"  too many errors ({n_errors}), aborting")
                    break
                continue

        if args.limit and n_filed >= args.limit:
            print(f"  hit --limit {args.limit}, stopping")
            break

    elapsed = time.time() - started
    print(f"\nDone in {elapsed:.1f}s.")
    print(f"  filed:           {n_filed}")
    print(f"  skipped (binary): {n_skipped_binary}")
    print(f"  skipped (ext):    {n_skipped_ext}")
    print(f"  truncated:       {n_truncated}")
    print(f"  errors:          {n_errors}")

    if not args.dry_run:
        try:
            status = client.call_tool("mempalace_status", {})
            inner = json.loads(status["content"][0]["text"])
            print(f"\nPost-mine palace: total_drawers={inner.get('total_drawers')}, "
                  f"wings={list((inner.get('wings') or {}).keys())}")
        except Exception as exc:
            print(f"  (status probe failed: {exc})")

    return 0 if n_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
