# MemPalace Fork Hardening Changelog

## Version 1.0 — Security Hardening Pass (2026-04-09)

Comprehensive security hardening of the MemPalace fork for production use at Interactive Event Productions. All changes are backward-compatible unless noted.

---

### Fix 1: Query Sanitizer (PR #385 adaptation)
**File:** `mempalace/query_sanitizer.py` (NEW)
**File:** `mempalace/mcp_server.py` (MODIFIED)

**Problem:** AI agents prepend their system prompt to search queries, which causes ChromaDB semantic search to match on boilerplate instead of the actual question. PR #385 showed this tanks retrieval accuracy from 89.8% to 1.0%.

**Solution:** Four-stage cascading sanitizer that detects system-prompt contamination and extracts the real query. Stage 1 passes short clean queries through. Stage 2 extracts question sentences. Stage 3 grabs the tail sentence. Stage 4 truncates to the last 500 characters as a final fallback. The `tool_search` MCP function now accepts an optional `context` parameter so callers can separate background info from the search intent.

**Breaking changes:** The `tool_search` function signature gained a new optional `context` parameter. Existing callers are unaffected since it defaults to `None`.

**How to test:** Call `tool_search` with a long string that starts with system prompt text and ends with a real question. The `_sanitization` field in the response shows which stage was applied.

---

### Fix 2: ChromaDB Version Pin Tightened
**File:** `pyproject.toml` (MODIFIED)

**Problem:** The original pin `chromadb>=0.5.0,<0.7` allows a very wide range of versions, including potential breaking changes between 0.5.x and 0.6.x. For production, we want predictable behavior.

**Solution:** Tightened to `chromadb>=0.5.23,<0.6` which locks to the latest stable 0.5.x line and prevents accidental upgrade to 0.6.x (which has API changes). PyYAML also tightened to `>=6.0.2,<7`.

**Breaking changes:** If you were running ChromaDB 0.6.x, this will require a downgrade. Run `uv sync` or `pip install -e .` to update.

---

### Fix 3: Precompact Shell Hook Session ID Sanitization
**File:** `hooks/mempal_precompact_hook.sh` (MODIFIED)

**Problem:** The save hook (`mempal_save_hook.sh`) already sanitized `SESSION_ID` with a regex whitelist, but the precompact hook used the raw session ID directly from JSON. A crafted `session_id` like `../../etc/passwd` could write to arbitrary paths via the log file append.

**Solution:** Added the same Python-based sanitization: `re.sub(r'[^a-zA-Z0-9_\-]', '', sid)` with a 200-character cap, matching the save hook's approach.

---

### Fix 4: Codex Plugin Hook Name Whitelist
**File:** `.codex-plugin/hooks/mempal-hook.sh` (MODIFIED)

**Problem:** The hook accepted any string as the `$HOOK_NAME` argument and passed it directly to `python3 -m mempalace hook run --hook "$HOOK_NAME"`. While the Python side validates against a known set, the shell script should also validate to defense-in-depth.

**Solution:** Added a `case` statement that only allows `session-start`, `stop`, and `precompact`. Any other value exits with an error.

---

### Fix 5: MEMPAL_DIR Environment Variable Hardening
**File:** `mempalace/hooks_cli.py` (MODIFIED)

**Problem:** The `MEMPAL_DIR` environment variable was trusted if it pointed to any existing directory. An attacker who can control environment variables could point it at `/etc` or another user's home directory, causing MemPalace to process and index sensitive files.

**Solution:** New `_validate_mempal_dir()` function that resolves symlinks and requires the path to be under the user's `$HOME` directory. Rejected paths are logged.

---

### Fix 6: Hook Log Rotation
**File:** `mempalace/hooks_cli.py` (MODIFIED)

**Problem:** The `hook.log` file in `~/.mempalace/hook_state/` grows unbounded. On a system with frequent saves, this can consume significant disk space over time.

**Solution:** Added `_rotate_log()` function that rotates the log when it exceeds 5 MB, keeping up to 3 backup copies (`hook.log.1`, `hook.log.2`, `hook.log.3`). Configured via `MAX_LOG_SIZE` and `MAX_LOG_BACKUPS` constants.

---

### Fix 7: Restrictive File Permissions on State Files
**File:** `mempalace/hooks_cli.py` (MODIFIED)

**Problem:** Session state files (`{session_id}_last_save`) and the hook state directory were created with default OS permissions, potentially allowing other users on a shared system to read session data.

**Solution:** The state directory is now created with `0o700` (owner-only access), log files with `0o600` (owner read/write), and individual `last_save` files with `0o600`. Uses `_ensure_state_dir()` helper called before all state file operations.

---

### Fix 8: Claude.ai Normalizer Field Detection
**File:** `mempalace/normalize.py` (MODIFIED)

**Problem:** The Claude.ai JSON export normalizer only looked for `role`/`content` fields. Newer Claude.ai export formats use `sender` instead of `role`, and `text` or `body` instead of `content`. These conversations would silently fail to parse, producing no transcript output.

**Solution:** New `_extract_role_and_text()` helper that tries field names in order of likelihood: `role` then `sender` then `author` for the role, and `content` then `text` then `body` for the message text. This is used by both the flat-list and privacy-export code paths.

---

### Fix 9: CRLF Line Ending Normalization
**Files:** All `.sh` files in `hooks/`, `.claude-plugin/hooks/`, `.codex-plugin/hooks/`

**Problem:** Shell scripts had Windows-style CRLF line endings, which caused heredoc terminators to fail on Unix/macOS (the `HOOKJSON\r` terminator doesn't match `HOOKJSON`). This would cause the precompact and save hooks to fail silently.

**Solution:** Converted all shell scripts to Unix LF line endings.

---

### Pre-existing Fixes Already in Fork (from merged PRs)

These were already present in the codebase when we started:

- **PR #387 (Input Hardening):** `sanitize_name()` and `sanitize_content()` in `config.py`, applied at all MCP write entry points. SHA256 hashing, 10MB file size limits, symlink detection.
- **PR #188 (Session ID in Python hooks):** `_sanitize_session_id()` in `hooks_cli.py` with `re.sub(r"[^a-zA-Z0-9_-]", "", session_id)`.
- **Write-Ahead Log:** All MCP write operations logged to `~/.mempalace/wal/write_log.jsonl` with timestamps.
- **Safe subprocess calls:** All subprocess invocations use list form (no `shell=True`), with timeout protection on synchronous calls.

---

## Version 2.0 — Deep Audit + Event Production Personalization (2026-04-09)

Second pass: comprehensive security audit across the entire codebase, followed by personalization for Interactive Event Productions. All 85 existing tests pass.

---

### Fix 10: CRITICAL — Input Validation on ALL Read-Path Parameters
**File:** `mempalace/mcp_server.py` (MODIFIED)

**Problem:** While write operations (`tool_add_drawer`, `tool_kg_add`) validated wing/room/entity inputs via `sanitize_name()`, the read operations (`tool_list_rooms`, `tool_search`, `tool_traverse_graph`, `tool_find_tunnels`, `tool_kg_query`, `tool_kg_timeline`, `tool_diary_read`) passed user input directly to ChromaDB and SQLite queries without sanitization. This created an inconsistent security boundary — writes were hardened but reads were not.

**Solution:** Applied `sanitize_name()` validation to every function that accepts wing, room, entity, start_room, wing_a, wing_b, or agent_name parameters. Invalid inputs now return an error dict instead of being passed to the database layer.

---

### Fix 11: CRITICAL — TOCTOU Race Condition in Hook State Files
**File:** `mempalace/hooks_cli.py` (MODIFIED)

**Problem:** The hook's `last_save` state files were read and written with normal `read_text()`/`write_text()` operations. If two hook invocations ran concurrently (possible during rapid-fire saves), one could read a partially-written file or both could trigger saves simultaneously.

**Solution:** New `_atomic_write()` helper that writes to a temporary file in the same directory, then calls `os.replace()` (which is atomic on POSIX filesystems). This eliminates the window where a concurrent reader could see incomplete data.

---

### Fix 12: HIGH — Drawer ID Format Validation
**File:** `mempalace/mcp_server.py` (MODIFIED)

**Problem:** `tool_delete_drawer` accepted any string as a drawer_id without format validation. An attacker could fuzz with malformed IDs to probe the database or trigger unexpected behavior.

**Solution:** Added regex validation requiring drawer IDs to match the pattern `^(drawer|diary)_[a-zA-Z0-9_]+_[a-f0-9]{12,24}$`, which matches the actual format generated by `tool_add_drawer` and `tool_diary_write`.

---

### Fix 13: HIGH — Knowledge Graph Sanitization Gap
**File:** `mempalace/mcp_server.py` (MODIFIED)

**Problem:** `tool_kg_invalidate` passed subject, predicate, and object directly to the knowledge graph without validation. `tool_kg_query` and `tool_kg_timeline` passed entity names without validation. Date parameters (`as_of`, `valid_from`, `ended`) accepted any string without format checking.

**Solution:** Applied `sanitize_name()` to all entity/predicate/object parameters. Added ISO date format validation (`YYYY-MM-DD` regex) for all date parameters. Added `direction` parameter whitelist for `tool_kg_query`.

---

### Fix 14: HIGH — MEMPAL_DIR /tmp Allowance Removed
**File:** `mempalace/hooks_cli.py` (MODIFIED)

**Problem:** Version 1.0's `_validate_mempal_dir()` allowed paths under `/tmp` "for testing." This created a bypass: an attacker could set `MEMPAL_DIR=/tmp/../../etc/cron.d/` and the symlink-resolved path might still start with `/tmp`.

**Solution:** Removed the `/tmp` allowance entirely. MEMPAL_DIR must resolve to a path under the user's `$HOME` directory. Tests updated to mock `Path.home()` instead of relying on `/tmp`.

---

### Fix 15: MEDIUM — Numeric Parameter Bounds Checking
**File:** `mempalace/mcp_server.py` (MODIFIED)

**Problem:** Numeric parameters like `limit`, `max_hops`, `threshold`, and `last_n` had no bounds checking. A caller could request `limit=999999` results, `max_hops=999` graph traversals, or `threshold=-1.0` similarity matches, causing DoS or unexpected behavior.

**Solution:** All numeric parameters are now clamped to safe ranges: `limit` is 1-50, `max_hops` is 1-10, `threshold` is 0.0-1.0, `last_n` is 1-100.

---

### Fix 16: Test Suite Updated for Security Changes
**File:** `tests/test_hooks_cli.py` (MODIFIED)

**Problem:** Three existing tests used `/tmp` paths for MEMPAL_DIR and expected subprocess calls to succeed. After removing the `/tmp` allowance, these tests failed.

**Solution:** Updated `test_maybe_auto_ingest_with_env`, `test_precompact_with_mempal_dir`, and `test_precompact_with_mempal_dir_oserror` to mock `Path.home()` so the test's temp directory appears to be under HOME. Added new `test_maybe_auto_ingest_rejects_tmp` test that verifies paths outside HOME are properly rejected. All 85 tests pass.

---

### Personalization 1: Event Production Wing & Hall Configuration
**File:** `mempalace/config.py` (MODIFIED)

Default topic wings changed from generic personal/technical categories to event production categories: `events`, `venues`, `vendors`, `timelines`, `budgets`, `team`, `clients`, `productions`, `equipment`, `creative`, `technical`. Hall keywords populated with 10-12 domain-specific terms per wing (e.g., "gala," "wedding," "corporate" for events; "caterer," "florist," "contract" for vendors).

---

### Personalization 2: AAAK Dialect & Protocol Text
**File:** `mempalace/mcp_server.py` (MODIFIED)

`PALACE_PROTOCOL` updated with event-specific instructions: check vendor/venue/client facts before responding, save venue decisions and budget approvals, search client history before calls. `AAAK_SPEC` updated with event entity codes, event-specific halls (`hall_event_decisions`, `hall_vendor_notes`, etc.), and event-specific wings. Example changed to show event production data format.

---

### Personalization 3: Hook Save Messages
**File:** `mempalace/hooks_cli.py` (MODIFIED)

`STOP_BLOCK_REASON` and `PRECOMPACT_BLOCK_REASON` updated to instruct AI agents to focus on saving venue decisions, vendor updates, timeline changes, budget approvals, client preferences, equipment specs, and production notes — instead of generic "topics, decisions, quotes."

---

### Personalization 4: Room Detection Patterns
**File:** `mempalace/room_detector_local.py` (MODIFIED)

Added 40+ event production folder-to-room mappings: `venue`/`venues`/`location`/`floorplan` map to `venue-setup`, `vendor`/`caterer`/`contracts` map to `vendor-coordination`, `timeline`/`runsheet`/`schedule` map to `timeline-planning`, plus `production-notes`, `equipment-specs`, `guest-management`, and `creative-design` rooms.

---

### Personalization 5: Content Extraction Markers
**File:** `mempalace/general_extractor.py` (MODIFIED)

Added event-specific decision markers (venue selection, vendor choice, budget approval, contract signing) and milestone markers (venue confirmed, vendor contracted, event completed, load-in done, rehearsal complete, guest count finalized). These help the extraction engine recognize event production decisions and milestones in conversation text.

---

### Remaining Known Issues (Tracked, Not Yet Fixed)

These items were identified in the audit but are lower priority or require architectural changes:

1. **No rate limiting on MCP server** — a malicious client could spam requests. Recommended for a future version.
2. **Unbounded `collection.get()` calls** — `tool_status`, `tool_list_rooms`, and `tool_get_taxonomy` use `limit=10000`. For palaces with 100K+ drawers, this could cause memory pressure. Pagination recommended.
3. **Wikipedia API response validation** — `entity_registry.py` fetches and deserializes Wikipedia JSON without schema validation. Low risk since Wikipedia is a trusted source, but could be hardened.
4. **No encryption at rest** — palace database and WAL files are stored in plaintext. Optional AES-256-GCM encryption would be a good future addition.
5. **Error messages may leak internal paths** — some exception handlers return full error strings. A future pass should sanitize error responses to remove file paths and stack traces.

---

## Version 3.0 — StdioProxy Buffer Corruption Fix (2026-05-04)

Repair to the HTTP→stdio bridge that wraps the upstream MCP server. Two failure modes were observed in production:

  - **Failure A (timeouts):** every tool call hit a multi-minute timeout — discovery (`tool_search`) returned schemas correctly, but operational endpoints (`mempalace_status`, `mempalace_add_drawer`, etc.) didn't return.
  - **Failure B (wrong-shape returns):** some calls returned the wrong handler's payload — e.g. `mempalace_kg_query` got a `status`-shaped response, `mempalace_list_wings` got a `traverse`-shaped response, `mempalace_check_duplicate` got a `kg_query`-shaped response. Reproducible across two sessions on 2026-04-30 and 2026-05-04.

Module version: `mempalace/http_server.py` 0.1 → 0.2. Test suite: `tests/test_http_server.py` 0.1 → 0.2. All 24 HTTP-wrapper tests pass (20 pre-existing + 4 new buffer-corruption regression tests).

---

### Fix 18: HIGH — StdioProxy Buffer Corruption + Cold-Start Timeouts
**File:** `mempalace/http_server.py` (MODIFIED — v0.1 → v0.2)
**File:** `tests/test_http_server.py` (MODIFIED — v0.1 → v0.2)

**Problem:** `StdioProxy` proxies HTTP MCP requests to a single-threaded stdio subprocess (`mempalace.mcp_server`). Concurrent HTTP callers serialize on a single `asyncio.Lock` and each request reads exactly one line of subprocess stdout via `proc.stdout.readline()`. The proxy assumed a strict 1-line-per-response invariant.

That invariant breaks when a `readline()` is canceled mid-flight. The most common trigger is `healthcheck()` (used by `/ready`), which wraps `self.request(ping)` in an outer `asyncio.wait_for(timeout=HEALTH_TIMEOUT_SECONDS=5s)`. If the subprocess takes 5–30s to respond (perfectly normal during ChromaDB cold-start), the outer timeout fires:

  1. The inner `proc.stdout.readline()` is canceled. `asyncio.CancelledError` propagates.
  2. The `async with self._lock:` block releases the lock. **No `_restart()` is called** — restart only fires on the inner `asyncio.TimeoutError` raised at line 323.
  3. The subprocess's response *still arrives* in the OS pipe and the asyncio `StreamReader` buffer.
  4. The next legitimate HTTP request acquires the lock, writes its payload to stdin, calls `readline()` — and reads the **previous** request's response from the buffer.

That perfectly produces Failure B's wrong-handler-shape pattern: request N+1 receives request N's response, so a tool call appears to "work" but with stale data shaped for a different tool. Once a session falls into this state, every subsequent call is shifted by one — repeatedly returning prior tool's responses to current callers, which the user perceives as randomly-broken tool routing or generic `"Error occurred during tool execution"` failures when claude.ai's schema validator catches the mismatch.

Failure A (multi-minute timeouts on every operation) had a related root cause. `REQUEST_TIMEOUT_SECONDS` defaulted to 30s — too short for ChromaDB's first call after a cold subprocess (ONNX model load + first embedding can run 60–120s). The 30s timeout fires repeatedly, every restart cycle re-pays the cold-start cost, and the user observes the behavior as their MCP client's longer outer timeout (e.g. claude.ai's 5-minute MCP timeout). The buffer-corruption issue compounds this: even when the subprocess does eventually respond, the response was probably already misrouted.

**Solution:** Three concurrent fixes in `http_server.py`:

  1. **JSON-RPC id correlation in `_request_locked`.** After writing the request payload, loop on `readline()`. Compare `response.get("id")` to `payload.get("id")` and discard any mismatch as an orphan (with a warning log). After `MAX_ORPHAN_RESPONSES = 16` orphans, force `_restart()` and raise — the subprocess is misbehaving badly enough to abandon. This means cancellation orphans can no longer poison the next caller, regardless of where the cancellation originated.

  2. **`healthcheck()` now triggers `_restart()` on outer timeout.** Even with id-correlation tolerating buffer leftovers, a slow healthcheck signals the subprocess is in a bad state. Restarting now puts it back to a known-good state faster than waiting for the next real call to discover the problem. Backwards-compatible: `healthcheck()` still returns `False` on timeout — the new behavior is only the implicit subprocess restart.

  3. **`REQUEST_TIMEOUT_SECONDS` default raised 30s → 120s.** Still tunable via `MEMPALACE_REQUEST_TIMEOUT` env var. Reflects the reality that ChromaDB cold-start operations need more headroom than a warmed-up wrapper does.

**Breaking changes:** None. The id-correlation and restart behaviors are strictly additive; existing callers that didn't trigger the bug see no change. The timeout bump only enlarges the patience for slow operations — it doesn't change the behavior of fast ones.

**Operational changes:** Healthcheck-triggered restarts are now visible in logs as `healthcheck: outer timeout (>5s); subprocess unresponsive — restarting`. Orphan-response discards log as `stdio_proxy: discarding orphan response id=...`. Both are diagnostic — neither indicates user-facing failure. If you see a sustained stream of orphan-discard warnings, that's a sign of underlying subprocess instability worth investigating (memory pressure, ChromaDB DB lock, etc.).

**How to test:**
  1. Reconnect MemPalace in claude.ai, then run a sequence of tool calls — `mempalace_status`, then `mempalace_kg_query`, then `mempalace_list_wings`. All three should return correctly-shaped responses for their respective tools.
  2. Run `pytest tests/test_http_server.py -v` — 24 tests should pass, including 4 new tests covering the buffer-corruption fix: `test_stdio_proxy_discards_orphan_response_with_wrong_id`, `test_stdio_proxy_discards_multiple_orphans_then_returns_real`, `test_stdio_proxy_restarts_after_too_many_orphans`, `test_healthcheck_outer_timeout_triggers_restart`.
  3. Tail server logs while exercising MCP. Healthcheck timeouts will now show explicit restart messages; on a healthy session you should see no orphan-discard warnings.

**Rollback:** Revert this commit. The id-correlation logic, the healthcheck restart, and the timeout bump are all in one commit, so a single revert restores v0.1 behavior. Do not partial-revert: the three fixes are mutually reinforcing and behavior at intermediate states hasn't been tested.
