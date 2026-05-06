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

---

## Version 4.0 — OAuth Refresh Token Support (2026-05-04)

Targeted fix to the OAuth 2.1 provider used by Anthropic Connectors. Previously the access token expired after 1 hour with no way to refresh, forcing manual reconnect in claude.ai every hour. This version adds the standard `refresh_token` grant with single-use rotation, so reconnection is required only every 30 days (or after a detected token compromise).

Module version: `mempalace/oauth.py` 0.2 → 0.3. Test suite: `tests/test_oauth.py` 0.1 → 0.2. All 25 OAuth tests pass (16 pre-existing + 9 new).

Note on numbering: this is the second commit landed on main today after the V3.0 StdioProxy fix. Originally drafted as oauth-module v0.3 / changelog V3.0 on the feature branch, the changelog version was renumbered to V4.0 to slot in after V3.0=StdioProxy on main. The module version (oauth.py = v0.3) is unchanged from the feature-branch draft.

---

### Fix 19: HIGH — OAuth Access Tokens Expired Without Refresh Path
**File:** `mempalace/oauth.py` (MODIFIED — v0.2 → v0.3)
**File:** `tests/test_oauth.py` (MODIFIED — v0.1 → v0.2)

**Problem:** The `/oauth/token` endpoint only supported `client_credentials` and `authorization_code` grants. Both issued a JWT access token with a 1-hour TTL and no refresh mechanism. When the JWT expired, claude.ai's connector showed "Connection has expired" and the user had to manually click "Connect" — re-running the entire authorization_code+PKCE handshake. With the connector in active daily use, this meant 8–10+ reconnects per day, and several recent expiries appeared to occur mid-session, silently breaking MCP calls until the user noticed the banner.

The OAuth metadata at `/.well-known/oauth-authorization-server` advertised only `["authorization_code", "client_credentials"]` in `grant_types_supported`, so even if a client tried `grant_type=refresh_token` opportunistically, the server returned `unsupported_grant_type`.

**Solution:** Implemented the standard `refresh_token` grant per RFC 6749 §6 with single-use rotation per RFC 6749 §10.4:

1. **Refresh token issuance.** The `authorization_code` grant now returns BOTH `access_token` (JWT, 1h TTL — unchanged) AND `refresh_token` (opaque random string, 30-day TTL by default). Refresh tokens are deliberately opaque, not JWTs — verification needs server-side state for rotation/revocation anyway, so opaque tokens avoid duplicating that state in a JWT payload.

2. **Refresh token storage.** New module-level `_REFRESH_TOKENS` dict alongside the existing `_AUTHZ_CODES` dict. Single uvicorn worker (A4 constraint) means single-process; an in-memory dict is sufficient. Each entry records `client_id`, `scope`, `resource`, `expires_at`, `used`.

3. **Single-use rotation.** Each successful `grant_type=refresh_token` call marks the old RT as `used=True` and mints a fresh RT for the next refresh. The legitimate client always holds the most recent RT.

4. **Reuse detection.** Used RTs are deliberately NOT garbage-collected on use — they remain in the dict until natural expiry. If a stolen RT is replayed after the legitimate client has already rotated, the server returns `invalid_grant` with `"refresh_token already used"` rather than `"Unknown refresh_token"`. This preserves the RFC §10.4 compromise-indicator signal so the user can see (in logs) that someone else is trying to use their token.

5. **Server metadata.** `/.well-known/oauth-authorization-server` now advertises `"refresh_token"` in `grant_types_supported`, so Anthropic's connector backend knows it can use the new flow.

6. **New env var.** `MEMPALACE_OAUTH_REFRESH_TTL` (defaults to `2592000` = 30 days). Tunable independently of access-token TTL.

**Breaking changes:** None for users. The metadata change is backwards-compatible — clients that don't recognize `refresh_token` in `grant_types_supported` will simply ignore it and continue using `authorization_code`. The `authorization_code` response payload gains a new `refresh_token` field; clients that ignore unknown fields (which is most of them) are unaffected.

**Operational changes:** Each successful authorization_code or refresh now adds an entry to `_REFRESH_TOKENS`. The dict grows during the 30-day window, but with one user and single-digit refreshes per day, peak size is a few hundred entries — negligible memory impact. Used entries auto-evict at natural expiry via `_gc_expired_refresh_tokens()` on the next refresh request.

**How to test:**
1. Reconnect MemPalace in claude.ai; observe the connector status flips from "Expired" to "Connected".
2. Wait 1+ hour and use a MemPalace tool. Without v0.3 you'd see "Connection has expired"; with v0.3 the call succeeds because Anthropic silently refreshed the access token.
3. Run `pytest tests/test_oauth.py -v` — all 25 tests should pass, including the new `test_refresh_token_rotation_invalidates_old`, `test_refresh_token_grant_happy_path`, `test_refresh_token_client_mismatch_rejected`, etc.
4. Tail the server log; on a successful rotation you'll see `oauth: rotated refresh_token (grant=refresh_token)`. On an attempted reuse you'll see `oauth: refresh_token reuse detected — rejecting`.

**Rollback:** Revert this commit. The metadata change is backwards-compatible so clients keep working with `authorization_code` only — they'll just hit the expired-token problem again until reconnect.

---

## Version 5.0 — StdioProxy LimitOverrunError Fix on Large Search Responses (2026-05-04)

Follow-up to V3.0 (StdioProxy buffer corruption) and V4.0 (OAuth refresh). With those two fixes deployed, MemPalace was healthy for `status`, `traverse`, `kg_query`, `kg_stats`, and `list_rooms` — but every call to `mempalace_search` returned a generic execution error. The Coolify logs traced it to `asyncio.LimitOverrunError` raised inside `StdioProxy._request_locked`. Pre-existing bug, exposed once everything else was working.

Module version: `mempalace/http_server.py` 0.2 → 0.3. Test suite: `tests/test_http_server.py` 0.2 → 0.3. All 26 HTTP-wrapper tests pass (24 pre-existing + 2 new large-response regression tests).

---

### Fix 20: HIGH — `mempalace_search` Failing on Any Response > 64 KiB
**File:** `mempalace/http_server.py` (MODIFIED — v0.2 → v0.3)
**File:** `tests/test_http_server.py` (MODIFIED — v0.2 → v0.3)

**Problem:** The MCP subprocess emits one JSON-RPC response per line of stdout. The proxy reads each response with `await proc.stdout.readline()`. Asyncio's `StreamReader` defaults to a per-line read limit of **64 KiB** (set when `create_subprocess_exec` constructs the reader without a `limit=` argument). Any response longer than that raises `asyncio.LimitOverrunError("Separator is found, but chunk is longer than limit")` and the proxy errors out the whole tool call.

`mempalace_search` returns up to `limit` (default 5) drawer hits, *each including the verbatim drawer content*. A single mid-sized drawer (a long conversation transcript, a multi-page document) plus JSON envelope easily exceeded 64 KiB on its own, and any combination of multiple results made it certain. The bug was masked before V3.0/V4.0 because the proxy was already crashing for other reasons; once those were fixed, this became the dominant failure mode for the search path specifically.

The error trace from production confirmed the exact location:

```
asyncio.exceptions.LimitOverrunError: Separator is found, but chunk is longer than limit
File "/venv/lib/python3.12/site-packages/mempalace/http_server.py", line 297, in request
```

**Solution:** Two-line code change plus explicit error handling:

  1. **Pass `limit=STDOUT_LINE_LIMIT` to `create_subprocess_exec`.** The new module-level `STDOUT_LINE_LIMIT` constant defaults to **10 MiB** (`10 * 1024 * 1024`), tunable via the `MEMPALACE_STDOUT_LINE_LIMIT` env var. This is large enough to handle any realistic palace search payload while still bounding memory in the worst case.

  2. **Catch `asyncio.LimitOverrunError` in `_request_locked`** as a distinct exception. If a single response line ever exceeds even the 10 MiB ceiling, the proxy logs the size, restarts the subprocess to clear any partial state, and raises a clear `RuntimeError` to the HTTP caller (instead of leaking the asyncio-internal exception name into the MCP error path).

  3. **New tests in `tests/test_http_server.py`:** `test_stdio_proxy_handles_large_response_line` spawns a fake subprocess that emits a 200 KiB response (well over the 64 KiB asyncio default but well under the new 10 MiB limit) and verifies the payload round-trips intact. `test_stdio_proxy_subprocess_uses_v3_line_limit` guards against accidentally regressing the constant below 1 MiB.

**Breaking changes:** None. Behavior is strictly additive — responses that fit under 64 KiB before still work; responses that exceeded 64 KiB now also work. The new env var is optional.

**Operational changes:** Memory ceiling per in-flight request is now bounded by `STDOUT_LINE_LIMIT` (10 MiB by default) rather than asyncio's hidden 64 KiB. With single-uvicorn-worker (A4) this is one buffer at a time. If a deploy is memory-bound (very small VM), set `MEMPALACE_STDOUT_LINE_LIMIT=2097152` (2 MiB) or similar — search may fail on truly massive results but the per-request memory footprint stays small.

**How to test:**
  1. After redeploy, run `mempalace_search query="anything" limit=5` from the MemPalace connector. With a populated palace, this previously errored; with v0.3 it returns the expected hit list.
  2. Run `pytest tests/test_http_server.py -v` — 26/26 should pass, including the two new v0.3 tests.
  3. Tail server logs while exercising search. With v0.3 you should see no `LimitOverrunError` mentions in normal operation. If one does appear (>10 MiB single response), it's now a clearly logged and recovered-from event rather than a session-corrupting crash.

**Rollback:** Revert this commit. If deployed, search fails again on any response > 64 KiB — but no other tools regress.

---

## Version 6.0 — KG Auto-Extract Foundation (2026-05-04)

The KG layer (KnowledgeGraph class, sqlite, temporal validity, queries) has shipped since day one but never had an automatic population path — every drawer added via `mempalace_add_drawer` went into ChromaDB and nowhere else, leaving the KG dormant with 0 entities and 0 triples. v6.0 wires the missing connection: every drawer can now flow through an Anthropic-API-backed extractor that emits `(subject, predicate, object)` triples bound to a v0.1 vocabulary, with structured cost telemetry and anomaly detection.

This release adds the foundation but does NOT change any default runtime behavior — auto-extraction is gated behind `MEMPALACE_KG_AUTO_EXTRACT=true` (default `false`), and the bulk-backfill is opt-in via the new CLI subcommand. Deploying v6.0 is a no-op until the operator flips the flag.

Module versions: NEW `mempalace/kg_extractor.py` v0.1, NEW `mempalace/kg_extract_log.py` v0.1, NEW `mempalace/kg_backfill.py` v0.1, modified `mempalace/mcp_server.py` (post-add hook), `mempalace/cli.py` (kg-backfill subcommand), `pyproject.toml` (added `anthropic>=0.40` to `[http]` extra). All 89 existing-and-new tests pass.

---

### Fix 21: NEW — KG Auto-Extract Module + Vocabulary v0.1

**File:** `mempalace/kg_extractor.py` (NEW — 433 lines)

Pulls structured triples out of drawer content via the Anthropic API (Haiku 4.5 by default — fast, ~$0.0005 per drawer). The module is the single API surface that both `tool_add_drawer` and the bulk-backfill use; it ensures both paths emit triples against the same vocabulary and write to the same telemetry log.

**Vocabulary v0.1** (grounded in samples from the user's actual content — Atlas PRDs, TECHNICAL_CHANGELOGs, AI Governance, deployment session logs, audit baselines, schema docs):

  - **12 entity types:** Person, Organization, Project, Component, Document, Version, Decision, Finding, Event, Technology, Service, Phase.
  - **25 predicates** grouped: people/orgs (`member_of`, `works_with`, `authored`, `assigned_to`), project structure (`part_of`, `owned_by`, `integrates_with`), versioning (`has_version`, `supersedes`, `tagged_as`, `at_phase`), status (`has_status`, `is_locked`), documents (`documented_in`, `references`, `governed_by`), technical (`depends_on`, `uses`, `runs_on`, `pinned_to`, `deployed_at`), findings/decisions (`identified_in`, `resolved_by`, `blocks`, `decided_at`).

**Flexible-evolving discipline:** the model is told to prefer the known vocabulary but is allowed to coin new predicates when nothing fits, marked with `novel_predicate=true`. The parser cross-checks the model's self-report against `KNOWN_PREDICATES` and overrides in both directions (catches both "model lied about novelty" and "model coined a known predicate"). Every novel predicate logs at INFO with subject/object so the operator has a weekly review queue ready to grow the vocabulary deliberately.

**Robustness:** the function never raises. ANY failure (missing API key, API timeout, malformed JSON, prose-wrapped JSON, individual triple malformed) is caught and logged; caller gets `[]`. Input truncated at 30 KiB to bound cost. Confidence-below-threshold (0.5) triples dropped at parse time.

**Coverage:** 24 unit tests — vocabulary sanity, code-fence stripping, JSON salvage from prose-wrapped responses, novel-predicate cross-check both directions, predicate snake_case normalization, entity-type whitelisting, oversize-input truncation, API-failure swallowing, missing-key handling.

---

### Fix 22: NEW — KG Extract Transaction Log (Cost Telemetry + Anomaly Detection)

**File:** `mempalace/kg_extract_log.py` (NEW — 377 lines)

Every call to `extract_triples()` now writes a row to a SQLite log co-located with the KG database. This gives operators auditable cost totals over time + automatic flagging of runaway spend before it accumulates.

**Tracked per call:** timestamp, source (`tool_add_drawer` / `kg-backfill` / `manual`), drawer_id (when applicable), model used, input/output tokens, USD cost (computed from configurable rates), triples extracted, novel-predicate count, duration ms, status (`success`/`error`/`no_api_key`/`too_short`), error message (when applicable), anomaly flag.

**Cost rates** (defaults from current Haiku 4.5 public pricing) tunable via env: `MEMPALACE_KG_PRICE_INPUT_PER_M` (default 0.80), `MEMPALACE_KG_PRICE_OUTPUT_PER_M` (default 4.00).

**Anomaly detection** flags any successful call where EITHER:
  - `cost_usd > MEMPALACE_KG_COST_ABSOLUTE_CEILING` (default $0.50 per call), OR
  - `cost_usd > 3 × p95(last 50 successful calls)` — silent below the 10-call baseline to avoid noise on fresh deployments.

Flagging is informational (logs at WARNING + writes the reason to the row); the call itself still succeeds and the triples still land. A grep over container logs surfaces every flagged call for review.

**Reporting API:** `summarize(window_days=N, source=...)` aggregates calls / errors / skipped / total-cost-USD / p50/p95/max/avg-cost / total-triples / total-novel-predicates / anomalies-flagged / first-call / last-call.

**Coverage:** 14 unit tests — cost math at default rates and with env overrides, success/error/skipped status separation, absolute-ceiling anomaly detection, p95-multiplier anomaly detection, baseline minimum (no-flag below 10 calls), per-source filtering, percentile correctness on real data, graceful empty-log handling.

---

### Fix 23: NEW — `tool_add_drawer` Post-Add Auto-Extract Hook

**File:** `mempalace/mcp_server.py` (MODIFIED — `tool_add_drawer`)

After a successful `col.upsert` of a drawer, when `MEMPALACE_KG_AUTO_EXTRACT=true` (default `false`) the drawer content is sent to `extract_triples()` and each result is persisted via `_kg.add_triple` with `source_file=drawer:<drawer_id>` so the KG can trace any fact back to the drawer it came from. Entity types, when known, are persisted via `_kg.add_entity` so the entities table gets typed correctly.

**Default off** means deploying v6.0 changes nothing operationally until the operator flips the env var. This is deliberate — the foundation deploys at zero risk, and the cost-incurring behavior change is a separate, deliberate Coolify env-var edit by the operator.

**Failure isolation:** the hook is wrapped in nested try/except. Any failure in extraction, in `add_entity`, in `add_triple`, or anywhere else logs at EXCEPTION level but the underlying drawer write itself remains successful. A drawer that fails to extract triples is still a successfully-filed drawer.

The response payload gains an optional `triples_extracted: int` field when the hook ran, so callers can see at a glance how much KG content the drawer produced.

---

### Fix 24: NEW — `mempalace kg-backfill` CLI Subcommand

**File:** `mempalace/kg_backfill.py` (NEW — 317 lines)
**File:** `mempalace/cli.py` (MODIFIED — new subparser + dispatch entry)

One-time / incremental bulk-extraction over the ~1,636 drawers that already exist in the palace before v6.0 wiring. Walks the ChromaDB collection in 500-drawer batches, calls `extract_triples()` on each, persists triples to KG.

**Cost discipline built in:**
  1. Pre-run scan counts drawers and prints estimated cost (uses `AVG_INPUT_TOKENS_PER_DRAWER × count × Haiku rates`).
  2. Confirmation prompt — operator must type `yes` — unless `--yes` is passed for scripted runs.
  3. `--dry-run` skips the API entirely, just reports the estimate.
  4. `--limit N` for incremental top-up runs.
  5. Every call goes through `kg_extract_log` so anomaly flagging fires during the run if any single drawer's cost is unexpectedly high.
  6. `--stats` mode (with `--stats-source` and `--stats-window-days` filters) prints log totals and recent anomalies without running anything.

**Idempotent:** re-running is safe. `KnowledgeGraph.add_triple` already de-dups identical `(subject, predicate, object, valid_to IS NULL)`, so repeated runs that re-extract the same drawer mostly produce dropped duplicates at the KG layer.

**Resumable:** Ctrl-C between drawers stops cleanly and prints partial-run stats. The kg_extract_log already has the rows for the calls that completed, so the summary view is accurate even after an abort.

---

### Operational notes

**To enable auto-extraction on new drawers** (after deploy):
  1. Add `ANTHROPIC_API_KEY` to Coolify Environment Variables → Save.
  2. Add `MEMPALACE_KG_AUTO_EXTRACT=true` to Coolify Environment Variables → Save.
  3. Coolify auto-deploys; new drawers begin emitting triples on the next add.

**To bootstrap the KG over existing drawers**:
  1. Coolify → mempalace:main → Terminal.
  2. Run `mempalace kg-backfill --dry-run` first to see drawer count + cost estimate.
  3. Run `mempalace kg-backfill --limit 10` to spot-check quality on a small batch.
  4. Run `mempalace kg-backfill --yes` for the full backfill.
  5. Verify with `mempalace kg-backfill --stats` and `mempalace_kg_stats` MCP tool.

**To audit cost over time:**
  - `mempalace kg-backfill --stats` (all sources, all time)
  - `mempalace kg-backfill --stats --stats-window-days 7` (last week)
  - `mempalace kg-backfill --stats --stats-source tool_add_drawer` (just per-drawer auto-extract calls)

**Rollback:** revert this commit. The KG remains as-is (any triples already extracted stay; no schema change to back out). The auto-extract hook, the backfill CLI, and the cost log are all gone — no behavior beyond what existed before v6.0.

---

## Version 6.1 — Subscription-Side KG Extraction Path (2026-05-04)

Follow-up to v6.0 in response to "why does this need an Anthropic API key when I already pay for a Claude.ai subscription?". v6.1 adds a single MCP tool that lets a Cowork scheduled task walk the palace and extract triples using the operator's existing claude.ai subscription — zero API spend, no separate billing account, no env var needed.

The v6.0 server-side hook + API path remains in place but inert (default-off flag). The two extraction paths now coexist; operators pick whichever they prefer based on their realtime-vs-cost trade-off.

---

### Fix 25: NEW — `mempalace_list_unextracted_drawers` MCP Tool

**File:** `mempalace/mcp_server.py` (NEW tool + handler + TOOLS-dict entry)
**File:** `mempalace/knowledge_graph.py` (NEW helper method)

**Problem:** v6.0 shipped two extraction paths — the inline `tool_add_drawer` post-add hook (gated by `MEMPALACE_KG_AUTO_EXTRACT`) and the `mempalace kg-backfill` CLI. Both call the Anthropic API directly, which requires the operator to provision an `ANTHROPIC_API_KEY` env var with separate billing. For an operator who already has a Claude.ai (or Cowork) subscription, that's a redundant payment for the same compute they're already buying.

**Solution:** Expose a new MCP read tool that returns drawers without any KG triples filed against them, so a Cowork scheduled task can use the operator's existing subscription to walk the queue:

  - **`KnowledgeGraph.list_source_drawer_ids() -> set[str]`** — new helper method. Queries `triples` for `source_file LIKE 'drawer:%'`, strips the prefix, returns the set of drawer IDs that already have at least one triple. Returns an empty set on any error so an uninitialized KG db doesn't break the read tool.

  - **`mempalace_list_unextracted_drawers(limit=50, since_date=None)`** — new MCP tool. Walks the ChromaDB collection in 500-drawer batches, filters out drawers in the extracted-set, optionally filters by `metadata.filed_at >= since_date`, returns up to `limit` drawers (1–200, default 50) with full content + metadata. Also returns `total_unextracted` so the caller can see how big the queue still is.

The tool description in `TOOLS` includes explicit guidance for an LLM agent: "for each returned drawer, extract subject-predicate-object triples using the v0.1 vocabulary, then persist via `mempalace_kg_add`." A scheduled-task Claude reads that description as part of its tool catalog.

**Why this is the optimal path for operators with a Claude.ai subscription:**

  1. The subscription already covers the inference compute. The API path is paying twice for the same model.
  2. A Cowork scheduled task is exactly the right granularity — daily or 6-hourly batches catch any drawers added since the last run and extract them, with no per-drawer latency cost on the write path.
  3. Anomaly detection is unnecessary here because there is no per-call dollar cost to monitor.
  4. The full chain (read drawer → reason about content → emit triples → write via `mempalace_kg_add`) all happens inside the user's subscription quota.

**Trade-off vs v6.0 server-side hook:**

  | | Subscription scheduled task | API-key server hook |
  | --- | --- | --- |
  | $/month | $0 | ~$1/mo at typical write rates |
  | Drawer → KG latency | up to N hours (interval) | seconds (real-time) |
  | Anomaly telemetry | n/a | built in |
  | Setup | one Cowork scheduled task | one Coolify env var |

Both paths share the same `source_file=drawer:<id>` linkage, so a triple's drawer of origin is queryable regardless of which path produced it. They also de-conflict naturally: the scheduled task only sees drawers without triples, so if the API-key hook runs first, the scheduled task simply skips that drawer next cycle.

**Breaking changes:** None. Pure additive — one new tool, one new helper method, no schema change, no behavior change to existing tools.

**How to test:**
  1. After deploy, in claude.ai or Cowork: call `mempalace_list_unextracted_drawers(limit=5)`. Expect 5 drawers (or fewer, if you've extracted some already) with content + metadata, plus a `total_unextracted` count.
  2. After the Cowork scheduled task runs once: call `mempalace_kg_stats`. Expect `entities > 0` and `triples > 0`.
  3. Re-call `mempalace_list_unextracted_drawers`: `total_unextracted` should have decreased by exactly the number of drawers the task processed.

**Operator next step (recommended, no API key path):**
  1. Cowork → scheduled tasks → Create scheduled task.
  2. Interval: every 6 hours (or daily — your call).
  3. Prompt: "Pull up to 50 unextracted drawers via mempalace_list_unextracted_drawers. For each one, read the content and extract subject-predicate-object triples using the v0.1 vocabulary [paste vocabulary]. Persist each triple via mempalace_kg_add(subject, predicate, object) with appropriate confidence and source_file=drawer:<id>. After all 50 are done, write a brief diary entry summarizing what you found."
  4. Initial backfill: trigger the task on-demand a few times (or run it manually from a chat) to chew through the 1,636 existing drawers.

**Rollback:** revert this commit. Tool disappears from the registry; existing triples remain (their `source_file` linkage is unchanged). The v6.0 API-key path is unaffected.

---

## Version 6.2 — Drawer Extraction Bookkeeping Fix (2026-05-05)

Follow-up to Fix 25 (`mempalace_list_unextracted_drawers`). Operator reported that the queue never drained: every drawer kept showing up as unextracted even after dozens of `kg_add` triples landed against specific drawer IDs. Diagnosed as a column-mismatch bug; fix is small and targeted.

---

### Fix 26: Bookkeep drawer extraction state across both source columns

**File:** `mempalace/knowledge_graph.py` (MODIFIED — `list_source_drawer_ids`)
**File:** `mempalace/mcp_server.py` (MODIFIED — tool descriptions for `mempalace_list_unextracted_drawers` and `mempalace_kg_add.source_closet`)
**File:** `tests/test_knowledge_graph.py` (NEW — `TestDrawerSourceBookkeeping` class)
**File:** `tests/test_mcp_server.py` (NEW — `test_kg_add_marks_drawer_as_extracted`)
**File:** `scripts/verify_drawer_bookkeeping_fix.py` (NEW — standalone verifier, no chromadb)
**File:** `scripts/backfill_drawer_extraction_state.py` (NEW — optional one-shot data-normalization, dry-run by default)

**Problem:** The `triples` table has two source-link columns: `source_file` and `source_closet`. Triples written by `tool_add_drawer`'s auto-extract hook and by `kg_backfill.py` set `source_file='drawer:<id>'`. Triples written by `tool_kg_add` (the MCP tool the scheduled-task Claude calls) set `source_closet='drawer:<id>'` — `source_file` is never populated by that path. `list_source_drawer_ids()` only inspected `source_file`, so every triple that came in via `kg_add` was invisible to the bookkeeping query and the underlying drawer stayed marked as unextracted forever.

Symptoms (reported on 2026-05-05): `mempalace_status` reports 1638 drawers, `mempalace_list_unextracted_drawers` reports 1638 unextracted; ~70 `kg_add` triples filed across ~30 drawers, every triple confirmed in `kg_query` results — yet none of those 30 drawers ever drop from the unextracted list.

**Solution:** Change the query in `KnowledgeGraph.list_source_drawer_ids()` to UNION both columns:

```sql
SELECT DISTINCT src FROM (
    SELECT source_file   AS src FROM triples WHERE source_file   LIKE 'drawer:%'
    UNION
    SELECT source_closet AS src FROM triples WHERE source_closet LIKE 'drawer:%'
)
```

A drawer counts as extracted if EITHER column on any of its triples points back to it. This preserves the existing `source_file` flow that auto-extract and `kg_backfill.py` rely on, AND captures the `source_closet` triples written by `tool_kg_add` calls. Smaller change than retrofitting `kg_add` to write both columns, and instantly counts every triple already in the database during the broken window — no schema change, no row updates.

Tool descriptions also corrected:

  - `mempalace_list_unextracted_drawers`: dropped the misleading "the source_file linkage back to the drawer is bookkept automatically" line; replaced with explicit guidance that the caller MUST pass `source_closet='drawer:<drawer_id>'` to `kg_add`.
  - `mempalace_kg_add.source_closet`: parameter description now says "for drawer-extraction workflows pass `drawer:<drawer_id>` so the drawer counts as extracted in `mempalace_list_unextracted_drawers`."

Version aligned: `mempalace/version.py` was drifting at `3.0.14` while `pyproject.toml` was at `3.0.14+iep.2`. Both bumped to `3.0.14+iep.3` so `test_version_consistency.py` continues to pass.

**Breaking changes:** None. Pure read-side fix; no schema change, no data change. Existing triples filed via either path continue to work.

**How to test:**
  1. Clean palace: file a drawer via `tool_add_drawer`, confirm it appears in `mempalace_list_unextracted_drawers`.
  2. Call `mempalace_kg_add(subject, predicate, object, source_closet='drawer:<id>')` against that drawer.
  3. Re-call `mempalace_list_unextracted_drawers` — `total_unextracted` should decrement by 1 and the drawer should NOT be in the returned list.
  4. Existing data: just re-call `mempalace_list_unextracted_drawers` after deploy. The ~30 drawers with `kg_add`-filed triples from the broken window should now drop from the queue immediately, no script needed.

**Optional data-normalization:** `scripts/backfill_drawer_extraction_state.py` copies `drawer:<id>` values between `source_file` and `source_closet` whenever one is NULL, so a future tool that reads only one column doesn't have the same blind spot. Dry-run by default; `--apply` to commit. Not required for the fix — the union query already handles the visible bug.

**Rollback:** revert this commit. The query goes back to single-column inspection and the bug returns. Triples in the database (including any normalized by the backfill script) remain valid; both columns are non-destructive.
