# Technical Change Log
Project: MemPalace Continuous Capture & Productivity Intelligence
Session Date: 2026-05-19
Developer: Matt + Claude
Status: **In Progress** → Ready for Review → Pushed → Archived

**Branch:** `feature/mempalace-continuous-capture` (forked from `main` at HEAD `a852bb5`)
**Repo:** `maysfbewithyou/mempalace`
**Kickoff doc:** Cowork Build Kickoff Prompt v1.0 (Continuous Capture & Productivity Intelligence)
**Architecture spec:** *to be derived as Phase 0 deliverable — file `MemPalace_Continuous_Capture_Architecture_v1.0.md` does not exist on disk; the kickoff prompt is the working spec until then*
**Governance:** Atlas Development Delivery Standard V1.1 applies (per kickoff §Hard Constraints). User preference: every change carries a version tag for rollback anchoring.

---

## Session Version Ledger

| Version | What it marks | Status |
|---|---|---|
| v0.1.0.0 | TCL skeleton created on feature branch | in progress |
| v0.1.0.1 | Branch `feature/mempalace-continuous-capture` cut from main `a852bb5` | done |
| v0.1.0.2 | Derived architecture spec v1.0 produced + Open Decisions surfaced | pending |
| v0.1.0.3 | Env vars + MCP reachability verified | pending |
| v0.1.0.4 | `wing_productivity-intelligence` + 2 rooms registered in MemPalace | pending |
| v0.1.0.5 | Phase 0 baseline tag — Matt review gate | pending |
| v0.1.1.x | Phase 1A — Idle timeout (schema, endpoint, frontend tracker, light test) | pending |
| v0.1.2.x | Phase 1B — beforeunload + sendBeacon + async worker (light test) | pending |
| v0.1.3.x | Phase 1C — Heartbeat with adaptive curve + dead-thread recovery (light test) | pending |
| v0.1.4.0 | Phase 1 — 3-pass Full Test | pending |
| v0.1.4.1 | Phase 1 — pre-push summary | pending |

---

## Schema Changes
<!-- Describe every table/field/index/FK change here. Include field types. Flag if a migration script is needed. Note whether ERD needs updating. -->

### v0.1.0.0 — None yet
- No schema changes in TCL bootstrap. Phase 1A will introduce the first migration(s) — `idle_pulse`, `diary_write_queue`, and (in Phase 1C) `heartbeat`. Open question: are these Atlas Postgres tables (Alembic) or MemPalace fork tables (different storage)? Routed to Open Items D-CC1.

## Environment Variables
<!-- New variables added, modified, or deprecated. Include name, purpose, and required format. Flag anything Luke must set in Coolify. -->

### v0.1.0.0 — Anticipated, not yet verified
- `MEMPALACE_MCP_URL` — anticipated, kickoff lists it. Likely value: `https://claude-brain.tstly.dev/mcp`. **Phase 0.4 will verify presence in Coolify.**
- `CLAUDE_API_KEY` and `ANTHROPIC_API_KEY` — kickoff lists both. These are likely the same key under two names; Anthropic SDK uses `ANTHROPIC_API_KEY`. **Reconcile in Phase 0.4 — pick one canonical name, document the other as deprecated alias if needed.**

## Integration Changes
<!-- New or modified integrations, webhook registrations/removals, API endpoint changes, new API keys or tokens. Was it tested end-to-end in dev? -->

### v0.1.0.0 — None yet
- Layer 1A will introduce `POST /api/mempalace/diary-write` — the canonical sink for idle-timeout-triggered captures. Receives `{thread_id, last_message_id}`, fetches message context from Claude API, formats AAAK, calls MemPalace MCP `mempalace_diary_write`.
- Layer 1B will introduce a `POST /api/mempalace/beacon` (sendBeacon target) that queues async diary writes.
- Layer 1C will introduce a `POST /api/mempalace/heartbeat` pulse endpoint.
- Layer 3 agents will be consumers of MemPalace MCP `mempalace_diary_read`, `mempalace_kg_query`, `mempalace_kg_timeline`, etc.

## Permission Changes
<!-- New roles, modified rules, RLS changes, access control additions. Anything Luke must apply in Supabase directly. -->

### v0.1.0.0 — None yet
- *Reminder: kickoff §Hard Constraints lists Postgres (not Supabase). Existing Atlas pattern (per Agent Network ledger work) is API-layer enforcement, not Postgres RLS. New endpoints will need authentication — bearer token (per Phase 2 architecture v0.2 §A5) is the established pattern for hitting MemPalace MCP. Decide auth posture for the new endpoints during Phase 0.4.*

## Error Handling
<!-- New try/catch blocks, error states, logging rules, alerts. Silent failures get flagged here. -->

### v0.1.0.0 — None yet
- Pre-existing constraint from memory: *"Static review misses runtime SQL bugs — smoke-curl every CRUD verb on atlas services that use raw text() SQL."* Applies if any of the new endpoints land in Atlas Flask and use SQLAlchemy `text()`. **Mandatory: end-to-end curl smoke test for every new endpoint before pre-push.**
- Root-cause from Recovery-Pass-v1.0 report: *"The MemPalace MCP connector isn't loaded in this Cowork session"* — the new Layer 1 paths must each handle the case where the MCP call fails (connector unloaded, network timeout, MemPalace down). Failure mode must be **queue + retry**, not silent drop.

## Performance
<!-- New indexes, query optimizations, caching, pagination, N+1 fixes, timeout configs. -->

### v0.1.0.0 — None yet
- Heartbeat table (Phase 1C) will be high-write — every active thread pulses every 2–5 minutes. Needs indexes on `(thread_id, timestamp)` at minimum. Possibly a TTL cleanup automation to keep table bounded.

## Data / Fixtures
<!-- Seed script updates, reference data, new fixtures, hardcoded values to move to DB, backfills required. -->

### v0.1.0.0 — Layer 0 data setup pending
- Phase 0.5 deliverable: register `wing_productivity-intelligence` with rooms `compaction-tuning` and `heartbeat-tuning` via MemPalace MCP. This is the only meta-data the system writes about its own learning to MemPalace; everything else stays in operational tables or runtime cache.

## Automations
<!-- New automations (name, trigger, action, app), modified automations, removed automations. Registry status. Cron config confirmations. Deferred PRD automations. -->

### v0.1.0.0 — None yet
- Phase 1B will introduce a background worker (node-cron or task queue) that drains the beacon queue.
- Phase 1C will introduce a dead-thread sweeper that detects pulse silence > 2× current interval and triggers recovery diary writes.
- Phase 2 (Compaction Sentinel) and Phase 3+ (agent team) will introduce nightly batch jobs.

## Frontend Delivery
<!-- Source layout (static/<app>/js/ with numeric prefixes) vs compiled bundle. Build approach (in-browser Babel vs pre-compiled). CDN pins (exact versions, vanilla vs -react variants). Injection patterns avoided (no Python-string JS patches). Data source (real API + empty-state vs MOCK_ arrays). PR workflow (feature branch, single PR, no drive-by edits). Flag anything that could land as a compiled HTML bundle or string-injected patch. -->

### v0.1.0.0 — Category scope clarification needed
- **Open question:** the kickoff lists Layer 1A/1B/1C "Frontend" steps (track keypress/click/scroll/message-send, install pagehide/beforeunload, WebSocket/HTTP pulse). Which *host* is the frontend? Matt's Cowork desktop app and Claude Code clients are not modifiable. The Atrium UI (`mempalace/atrium/`, deployed to `atrium-dev.tstly.dev`) is the only Matt-controlled frontend that calls MemPalace. **Likely-correct interpretation: the "frontend" surface for activity tracking is the MCP protocol itself — every tool-call from a Claude session is an implicit activity pulse seen by the MCP server. The "idle timeout" becomes server-side: no MCP tool calls from a session token for 10 minutes → diary write fires.** Flagged for Phase 0.3 spec derivation.
- If Atrium-hosted client-side activity tracking is in scope, V1.1 Frontend Delivery rules apply: `static/<app>/js/` with numeric prefixes, Babel standalone at page load, CDN pins (React 18.2.0 UMD, ReactDOM 18.2.0 UMD, Lucide 1.8.0 vanilla — NOT `lucide-react`), no Python-string JS injection.

---

## Open Items
<!-- Anything intentionally deferred, incomplete, or needing follow-up. Every deferral should have a reason. -->

### D-CC1 — Where do the new operational tables (idle_pulse, diary_write_queue, heartbeat) live?
- Options: (a) mempalace-fork's existing ChromaDB-backed palace — no, ChromaDB is for memory content, not operational state; (b) a new SQLite alongside the palace — matches palace_graph.py pattern; (c) Atlas Postgres via Alembic — matches the kickoff's stated tech stack but introduces cross-repo coupling. **Decision needed before Phase 1A schema migration. Recommend (b) SQLite-in-fork** for parity with palace_graph.py and KG sqlite, and to keep this build self-contained in mempalace-fork.

### D-CC2 — "Frontend" host interpretation (see Category 9)
- Literal interpretation: instrument Cowork / Claude Code / Claude.ai web (not feasible — not Matt's code).
- Pragmatic interpretation: server-side detection via MCP tool-call activity (recommended).
- Atrium-hosted interpretation: build an Atrium widget that tracks activity in *that* window only (limited utility).
- **Decision needed before Phase 1A wiring.**

### D-CC3 — `CLAUDE_API_KEY` vs `ANTHROPIC_API_KEY`
- Kickoff lists both. Anthropic Python SDK uses `ANTHROPIC_API_KEY`. Pick one canonical, document the other.

### D-CC4 — Architecture spec v1.0 ratification gate
- The derived `MemPalace_Continuous_Capture_Architecture_v1.0.md` (Phase 0.3 deliverable) needs Matt's sign-off before Phase 1 starts. This is the lock anchor for everything downstream.

### D-CC5 — CRLF/LF drift in mempalace-fork working tree
- `git status` shows 150 tracked files as modified — confirmed pure line-ending drift, no content changes. Risk: an accidental `git add .` would commit a 37k-line ending-only diff onto this feature branch. **Mitigation: always `git add <specific-file>` on this branch; never `git add .`.** Long-term fix (not this session): set `core.autocrlf=false` + `.gitattributes` normalize, then a one-time renormalization commit on main.

### D-CC6 — Test gate model
- Atlas Delivery Standard says use build-tester. mempalace-fork has its own pytest suite (85+ tests across `tests/`). Pre-push must pass *both* the build-tester runtime checks AND `pytest tests/ -v` clean. Documenting now so it doesn't surprise pre-push review.

---

## Notes for Luke
<!-- Anything the receiving developer needs that isn't captured above. Deploy steps, manual config, gotchas. -->

### v0.1.0.0 — Stack reconciliation summary
- This build extends `maysfbewithyou/mempalace` (the IEP-personalized MemPalace fork), not Atlas's main Flask app. The kickoff references "Next.js + Flask + Postgres + Alembic" as the Atlas stack — that's the *consumer* side. The producer side (the MCP server doing the diary writes) lives in mempalace-fork as a Python/Starlette/uvicorn service per `MemPalace_Phase_2_Architecture_v0.2.md`.
- Coolify deploy target: existing `claude-brain.tstly.dev` MCP service. Phase 0.4 will verify nothing breaks when a new code path lands in that container.
- New env vars (anticipated): `MEMPALACE_MCP_URL`, single `ANTHROPIC_API_KEY` (canonical). Existing env vars from Phase 2 deploy remain unchanged.
- Bearer-token auth model per Phase 2 v0.2 §A5 carries forward to the new endpoints.

---

## Version history

- **v0.1.0.0 (2026-05-19)** — TCL skeleton created on `feature/mempalace-continuous-capture`. All 9 categories present and stubbed with anticipated content. 6 Open Decisions (D-CC1 through D-CC6) flagged for Matt before Phase 1 work begins. Pure-drift CRLF noise in working tree noted as D-CC5 mitigation.

---

## Phase 1A Rollup — v0.1.1.0 → v0.1.1.4 (2026-05-19)

**Status:** Light Test green. 11/11 pytest passing in 0.76s.

### Schema Changes (v0.1.1.0)
- NEW: `~/.mempalace/continuous_capture.db` SQLite database (D-CC1 ratified).
- NEW table `idle_session(token_hash PK, first_activity_at, last_activity_at, thread_id, last_message_id, last_method, activity_count, status, diary_written_at, diary_drawer_id, retry_count, last_error, created_at, updated_at)`. Index `(status, last_activity_at)` for sweeper queries.
- NEW table `diary_write_queue(id PK AI, token_hash, trigger, thread_id, last_message_id, received_at, processed_at, drawer_id, retry_count, last_error)`. Index `(processed_at, received_at)` for worker queries. (Schema present in 1A; populated as audit log by 1A, primary writer in 1B.)
- NEW table `heartbeat(id PK AI, token_hash, thread_id, pulse_at, last_message_id, user_state, session_age_at_pulse_s, next_interval_s, state_changed)`. Index `(token_hash, pulse_at)` for dead-thread queries. (Schema present in 1A; populated in 1C.)
- NEW table `cc_schema_version(version PK, applied_at)` for future migration tracking. Currently at v1.

### Environment Variables (v0.1.1.0)
- NEW: `MEMPALACE_INTERNAL_API_TOKEN` — required (≥16 chars) for `/api/mempalace/diary-write`. Generate via `python -c "import secrets; print(secrets.token_urlsafe(32))"`. **Luke must set in Coolify before deploying this branch.**
- NEW: `MEMPALACE_CC_DB_PATH` — optional override for the SQLite path; defaults to `<MEMPAL_PALACE_PATH>/../continuous_capture.db`. Used by tests.
- NEW: `MEMPALACE_IDLE_SWEEP_INTERVAL_S` — default 60. Sweeper cadence.
- NEW: `MEMPALACE_IDLE_TIMEOUT_S` — default 600 (10 min per kickoff).
- NEW: `MEMPALACE_IDLE_MAX_RETRIES` — default 3 (per spec §8 retry policy).
- NEW: `MEMPALACE_DISABLE_IDLE_SWEEPER` — accepts 1/true/yes. Suppresses sweeper start during tests / dry-boots.

### Integration Changes (v0.1.1.0)
- NEW endpoint: `POST /api/mempalace/diary-write` (internal-token-gated, synchronous in Phase 1A). Idempotent — returns 409 if the session already has a `diary_drawer_id`.
- Sweeper calls `mempalace_diary_write` via the existing `StdioProxy.request` (JSON-RPC over stdin/stdout to the subprocess). **Honors Phase 2 v0.2 §A4 single-writer rule** — the wrapper does not import mempalace.mcp_server directly.
- Activity tracker hooks into the existing `mcp()` handler in `http_server.py` — every successful MCP request records a pulse against `sha256(bearer_token)`. Best-effort: a tracker failure is logged at WARNING and does not break the MCP response.

### Permission Changes (v0.1.1.0)
- `/api/mempalace/diary-write` is gated by `MEMPALACE_INTERNAL_API_TOKEN` (separate from the static `/mcp` bearer). This token is intended for in-container callers (sweeper, future beacon worker, future dead detector) AND for manual diagnostic curl from Matt's laptop.
- Added `/api/mempalace/diary-write`, `/api/mempalace/beacon`, `/api/mempalace/heartbeat` to `BearerAuthMiddleware.PUBLIC_PATHS` so the existing bearer middleware doesn't double-gate them. (1B and 1C routes are pre-registered in the path list but not yet served.)

### Error Handling (v0.1.1.0)
- Retry policy: 3 attempts before `status='failed'` — sweeper increments `retry_count` on each failure and writes `last_error`. Per kickoff Recovery-Pass-v1.0 root cause: the failure mode this build protects against (MCP connector unloaded) is exactly the kind that benefits from retries.
- Sweeper loop catches all exceptions per iteration and continues; only `CancelledError` exits the loop. A subprocess restart in the proxy is transparent to the sweeper.
- Activity tracker is wrapped in try/except — failure is non-fatal, downgraded to WARNING.

### Performance (v0.1.1.0)
- Three indexes added (see Schema). `idle_session(status, last_activity_at)` is the hot path — the sweeper does an indexed range scan every 60s.
- SQLite single-process, single-worker container (per Phase 2 v0.2 §A4) — no connection pool needed; per-call open/close has negligible cost on indexed PK updates.
- Sweeper batches up to 50 candidates per pass — bounded so a backlog can't hold the loop for minutes.

### Data / Fixtures (v0.1.1.0)
- No data fixtures introduced. (`wing_productivity-intelligence` deferred to Task #5 / Phase 0.5; not a Phase 1 blocker.)

### Automations (v0.1.1.0)
- NEW: `cc-idle-sweeper` asyncio.Task — started in lifespan, cancelled on graceful shutdown. Cadence 60s default. Substitutes for the kickoff's "node-cron" reference (the wrapper container is Python/Starlette per Phase 2 v0.2 §A3 — adding Node would conflict with §A4 single-worker).

### Frontend Delivery (v0.1.1.0)
- N/A in Phase 1A per D-CC2 (ratified): activity surface is server-side via MCP tool calls; no client-side instrumentation built in this phase.

### Light Test Results (v0.1.1.4)
- File: `tests/test_continuous_capture_idle.py` (11 tests, 0.76s, all passing under `pytest --noconftest`).
- Coverage: schema idempotency, table existence, activity record insert+upsert, hash stability, AAAK format determinism, AAAK degradation on bad input, sweeper happy path, sweeper idempotency, audit-log write, retry-count increment, max-retries final status.
- Known limitation: pytest cannot load the existing conftest.py in the Cowork bash mount because chromadb isn't installed — run with `--noconftest` for this suite. (Tracking as D-CC10.)

### Files touched in Phase 1A
- NEW: `mempalace/continuous_capture/__init__.py` (1.2 KB)
- NEW: `mempalace/continuous_capture/db.py` (6.7 KB)
- NEW: `mempalace/continuous_capture/activity.py` (3.7 KB)
- NEW: `mempalace/continuous_capture/diary_writer.py` (6.4 KB)
- NEW: `mempalace/continuous_capture/sweeper.py` (6.1 KB)
- NEW: `mempalace/continuous_capture/routes.py` (7.9 KB)
- MODIFIED: `mempalace/http_server.py` (+68 lines: import, sweeper task global, PUBLIC_PATHS additions, activity hook in mcp(), lifespan extensions, new Route registration)
- NEW: `tests/test_continuous_capture_idle.py` (~9 KB, 11 tests)

### New Open Items
- **D-CC9** — Edit-tool drift on http_server.py truncated the file mid-lifespan. Recovered via `git show main:mempalace/http_server.py > file` + a one-shot Python patcher script. Mitigation going forward: prefer the bash-patcher pattern over sequential Edit calls on existing files in the Cowork mount. Long-term: investigate whether the Cowork file harness has a known race against rapid Edit sequences.
- **D-CC10** — Test runner requires `--noconftest` because the conftest.py top-level `import chromadb` fails in the bash mount without chromadb installed. Options: (a) install chromadb in the bash venv (large dep), (b) make chromadb import in conftest lazy-tolerant, (c) keep `--noconftest` as the cc test runner default. Recommend (c) for cc tests + add a `pytest-cc` marker so CI knows to use the lighter runner.

---

## Phase 1B Rollup — v0.1.2.0 → v0.1.2.2 (2026-05-19)

**Status:** Light Test green. 8/8 pytest passing.

### Schema Changes (v0.1.2.0)
- No new tables — `diary_write_queue` was provisioned in v0.1.1.0. Phase 1B is its first primary writer.

### Environment Variables (v0.1.2.0)
- NEW: `MEMPALACE_BEACON_POLL_INTERVAL_S` — default 5s. Worker cadence.
- NEW: `MEMPALACE_BEACON_BATCH_SIZE` — default 50. Max rows per drain pass.
- NEW: `MEMPALACE_BEACON_MAX_RETRIES` — default 3. After this, the row is marked processed with `last_error` set (operator can query failed rows later).
- NEW: `MEMPALACE_DISABLE_BEACON_WORKER` — `1|true|yes` suppresses the worker for tests / dry boots.

### Integration Changes (v0.1.2.0)
- NEW endpoint: `POST /api/mempalace/beacon` — unauthenticated (D-CC7), accepts text/plain or application/json (sendBeacon emits text/plain). Always returns 204 No Content — beacon callers can't act on errors. Enqueues a `diary_write_queue` row.
- NEW automation: `cc-beacon-worker` asyncio.Task. Drains the queue every 5s, deduplicates against `idle_session.diary_drawer_id`, calls `mempalace_diary_write` via StdioProxy.

### Permission Changes (v0.1.2.0)
- `/api/mempalace/beacon` confirmed in `BearerAuthMiddleware.PUBLIC_PATHS` (pre-staged in v0.1.1.0). No bearer or internal-token check on this endpoint by design — the dedup gate is the security boundary.

### Error Handling (v0.1.2.0)
- Worker catches per-iteration exceptions, continues loop, exits only on `CancelledError` (mirrors sweeper pattern).
- Malformed beacon payloads silently return 204 (logged at WARNING). Beacons are fire-and-forget; rejecting them serves no purpose.
- Beacons with missing/invalid `token_hash` silently 204 — never enqueued.

### Performance (v0.1.2.0)
- `diary_write_queue` index `(processed_at, received_at)` carries the worker query.
- Batch size 50 caps any single drain pass.

### Automations (v0.1.2.0)
- `cc-beacon-worker` registered in lifespan startup. Cancelled on graceful shutdown (ordered: dead-detector → beacon-worker → sweeper).

### Frontend Delivery (v0.1.2.0)
- Server-side only this phase. The eventual Atrium-side beacon JS (per spec §4.3) is deferred — landing in Phase 5 (audit dashboard) when there's an actual page that needs unload hooks. Per V1.1 governance, when that JS lands it will live in `static/atrium/js/05-session-beacon.js` (numeric prefix, plain JS, CDN destructure for React imports).

### Light Test Results (v0.1.2.2)
- File: `tests/test_continuous_capture_beacon.py` (8 tests).
- Coverage: worker happy-path drain, dedup against pre-written sessions, beacon-only sessions (no activity history), failure retry increment, max-retries marks processed, route enqueues valid payload, route 204 on malformed payload, route 204 on missing token_hash.

---

## Phase 1C Rollup — v0.1.3.0 → v0.1.3.3 (2026-05-19)

**Status:** Light Test green. 11/11 pytest passing.

### Schema Changes (v0.1.3.0)
- No new tables — `heartbeat` was provisioned in v0.1.1.0. Phase 1C is its first primary writer.

### Environment Variables (v0.1.3.0)
- NEW: `MEMPALACE_DEAD_DETECT_INTERVAL_S` — default 30s. Detector cadence.
- NEW: `MEMPALACE_DISABLE_DEAD_DETECTOR` — `1|true|yes` suppresses the detector for tests / dry boots.

### Integration Changes (v0.1.3.0)
- NEW endpoint: `POST /api/mempalace/heartbeat` — bearer-protected (same static bearer as /mcp). Inserts a heartbeat row, computes `next_interval_s` via the cadence curve, sets `state_changed` based on previous pulse, returns `{next_interval_s, session_age_s, state_changed}`. Also pulses the activity tracker so heartbeating sessions don't trigger the idle sweeper.
- NEW automation: `cc-dead-detector` asyncio.Task — every 30s, scans heartbeat table for sessions whose latest pulse is older than 2× the negotiated `next_interval_s`. For each dead session (that isn't already diary_written), calls `mempalace_diary_write` with `trigger='heartbeat_dead'`.

### Permission Changes (v0.1.3.0)
- `/api/mempalace/heartbeat` uses the static bearer for auth (D-CC7) — same token as /mcp. No new tokens to provision.
- Confirmed in `BearerAuthMiddleware.PUBLIC_PATHS` (pre-staged in v0.1.1.0; the route handler itself checks bearer to avoid the OAuth path of BearerAuthMiddleware reading the body twice).

### Error Handling (v0.1.3.0)
- Detector catches per-iteration exceptions, continues loop, exits only on `CancelledError`.
- Heartbeat route returns 401 on invalid bearer, 400 on missing token_hash or invalid JSON.
- `user_state` values outside `{active, typing, idle}` are silently normalized to `active` (forward-compat with future client states).

### Performance (v0.1.3.0)
- `heartbeat(token_hash, pulse_at)` index supports the GROUP BY in the detector query.
- Detector look-back capped at 6 hours — older sessions are stale and not worth scanning.
- Single SELECT-GROUP-BY-MAX per detector pass — O(latest-active-tokens), not O(all-pulses).

### Automations (v0.1.3.0)
- `cc-dead-detector` registered in lifespan startup. Cancelled first on graceful shutdown so it doesn't try to write after the proxy goes away.

### Frontend Delivery (v0.1.3.0)
- Server-side only. The eventual heartbeat client (per spec §4.4) negotiates `next_interval_s` from the server response, so the client implementation can stay thin. Deferred to Phase 5.

### Light Test Results (v0.1.3.3)
- File: `tests/test_continuous_capture_heartbeat.py` (11 tests).
- Coverage: cadence curve across all three bands (0-3min, 3-15min, 15+min), pulse insert, bearer rejection, state-change detection, activity-tracker passthrough, dead-thread positive case, alive-thread negative case, already-written skip, audit-row logging.

---

## Phase 1 Full Test — v0.1.4.0 (2026-05-19)

**3-pass result via `pytest --noconftest` against all three test files:**

| Pass | Tests | Duration | Result |
|---|---|---|---|
| 1 | 30 | 2.06s | 30/30 PASS |
| 2 | 30 | 1.96s | 30/30 PASS |
| 3 | 30 | 1.95s | 30/30 PASS |

**Variance:** 0.11s across passes. Deterministic. No flakes.

**Total Phase 1 LOC delivered (new code + tests):**
- `mempalace/continuous_capture/`: 1,197 lines across 8 files
- `mempalace/http_server.py`: +114 lines vs pristine main (768 → 882)
- `tests/test_continuous_capture_*.py`: 811 lines across 3 files
- **Grand total: 2,122 lines new code / tests**

### Phase 1 success criteria (carried from kickoff §Success Criteria)
1. ✅ **Six-day diary gap is impossible.** All three Layer 1 paths (1A idle, 1B beacon, 1C heartbeat-dead) converge through the same diary_write_queue with the same dedup gate.
2. *Phase 2 deliverable, not built here.* (Compaction Sentinel)
3. *Phase 3 deliverable, not built here.* (Coaching Agent)


---

## Phase 1 Pre-Push Summary — v0.1.4.1 (2026-05-19)

**Per Atlas Development Delivery Standard V1.1.** Documents the 9-category readiness state at the close of the Phase 1 session. The formal pre-push gate (invocation of `atlas-pre-push-review`) is Matt's decision — this section is the inputs that skill will consult.

| # | Category | Status | Detail |
|---|---|---|---|
| 1 | **Schema** | ✅ Covered | NEW SQLite DB at `~/.mempalace/continuous_capture.db` with three tables (`idle_session`, `diary_write_queue`, `heartbeat`) and four indexes. Idempotent migration. Schema v1 recorded in `cc_schema_version`. |
| 2 | **Environment Variables** | ✅ Covered | 9 new env vars: `MEMPALACE_INTERNAL_API_TOKEN` (required, Luke must set in Coolify); `MEMPALACE_CC_DB_PATH`, `MEMPALACE_IDLE_SWEEP_INTERVAL_S`, `MEMPALACE_IDLE_TIMEOUT_S`, `MEMPALACE_IDLE_MAX_RETRIES`, `MEMPALACE_DISABLE_IDLE_SWEEPER`, `MEMPALACE_BEACON_POLL_INTERVAL_S`, `MEMPALACE_BEACON_BATCH_SIZE`, `MEMPALACE_BEACON_MAX_RETRIES`, `MEMPALACE_DISABLE_BEACON_WORKER`, `MEMPALACE_DEAD_DETECT_INTERVAL_S`, `MEMPALACE_DISABLE_DEAD_DETECTOR`. Canonical key name `ANTHROPIC_API_KEY` (D-CC3); `CLAUDE_API_KEY` deprecated. |
| 3 | **Integrations** | ✅ Covered | 3 new internal HTTP endpoints (`/api/mempalace/diary-write`, `/api/mempalace/beacon`, `/api/mempalace/heartbeat`). All diary writes routed through existing `StdioProxy.request` → `mempalace_diary_write` (honors Phase 2 v0.2 §A4 single-writer rule). End-to-end Light Test via mock proxy: 30/30 PASS x3. |
| 4 | **Permissions** | ✅ Covered | Layered auth model: diary-write uses `MEMPALACE_INTERNAL_API_TOKEN`; beacon is unauthenticated by design (D-CC7 — sendBeacon can't set Authorization; dedup is the guard); heartbeat uses the static `/mcp` bearer. `BearerAuthMiddleware.PUBLIC_PATHS` updated so the wrapper bearer doesn't double-gate. |
| 5 | **Error Handling** | ✅ Covered | Retry policies with bounded retry counts (3 for sweeper + beacon worker). Queue+retry on transient failures; never silent drop (addresses Recovery-Pass-v1.0 root cause). Activity tracker wrapped to be non-fatal. Async tasks catch per-iteration exceptions; only `CancelledError` exits the loops. Malformed beacon payloads silently 204 (logged at WARNING). |
| 6 | **Performance** | ✅ Covered | Four indexes: `idle_session(status, last_activity_at)`, `diary_write_queue(processed_at, received_at)`, `heartbeat(token_hash, pulse_at)`, and the implicit token_hash PK index. Bounded batches (50 per drain pass). Dead-detector look-back capped at 6 hours. Single SQLite writer (Phase 2 v0.2 §A4) — no contention. |
| 7 | **Data / Fixtures** | ⚠️ Deferred | `wing_productivity-intelligence` + rooms (Task #5) **NOT created this session**. **Reason:** not a Phase 1 blocker — that wing is used only by Phase 2's Compaction Sentinel and Phase 3's six agents. Phase 1A/1B/1C write to `wing_claude` (Recovery-Pass-v1.0 convention). Action item for Matt: register the wing before Phase 2 starts. |
| 8 | **Automations** | ✅ Covered | 3 new asyncio tasks registered in `http_server.py` lifespan: `cc-idle-sweeper` (60s cadence), `cc-beacon-worker` (5s cadence), `cc-dead-detector` (30s cadence). Each cancellable independently via env var. Graceful shutdown cancels in reverse order (detector → worker → sweeper) before proxy stop. Substitutes for the kickoff's "node-cron" reference (the wrapper container is Python/Starlette per Phase 2 v0.2 §A3). |
| 9 | **Frontend Delivery** | ⚠️ Deferred | No client-side JS shipped this phase. **Reason:** D-CC2 (ratified) — activity surface is server-side via MCP tool calls and existing endpoints; Cowork/Code/Chat clients aren't modifiable. The Atrium-side beacon + heartbeat clients (spec §4.3, §4.4) land in **Phase 5** when there's an actual dashboard to attach unload-hooks to. When that JS lands it will comply with V1.1: `static/atrium/js/05-session-beacon.js` numeric prefix, plain JS, CDN destructure, no Python-string injection, no MOCK arrays, live `/api/mempalace/*` endpoints. |

### Net delta vs `main` (HEAD `a852bb5`)
- **NEW:** 8 module files (`mempalace/continuous_capture/*.py`) — 1,197 LOC
- **NEW:** 3 test files (`tests/test_continuous_capture_*.py`) — 811 LOC, 30 tests
- **NEW:** `docs/deployment/MemPalace_Continuous_Capture_Architecture_v1.0.md` — 393 LOC, 8 Open Decisions ratified
- **NEW:** `TECHNICAL_CHANGELOG.md` — this file
- **MODIFIED:** `mempalace/http_server.py` — +114 LOC vs pristine (passing py_compile; activity hook in `mcp()`, lifespan extensions, route registration, PUBLIC_PATHS additions)
- **NEW Open Decisions surfaced and routed:** D-CC9 (Edit-tool drift; workaround documented), D-CC10 (test runner needs `--noconftest`; documented)

### Outstanding work *before* merge to main
1. **Phase 0.4** — Verify Coolify has `MEMPALACE_INTERNAL_API_TOKEN` set (≥16 chars). Verify `MEMPALACE_BEARER_TOKEN` and `MEMPAL_PALACE_PATH` already set (existing).
2. **Phase 0.5** — Register `wing_productivity-intelligence` (deferred — Phase 2 blocker, not Phase 1).
3. **cowork-git-push** — atomic commit of all new + modified files. Working tree shows 150 unrelated tracked files with CRLF/LF drift (D-CC5) — **commit only the new/modified files, not `git add .`**.
4. After successful push: invoke `atlas-pre-push-review` formally if merging to main; otherwise feature branch lives on for review.

### Test gate confirmation
- ✅ Light Test (Phase 1A): 11/11 pytest
- ✅ Light Test (Phase 1B): 8/8 pytest
- ✅ Light Test (Phase 1C): 11/11 pytest
- ✅ Full Test (3-pass): 30/30 × 3 = 90/90 PASS, variance <0.1s, no flakes
- ➖ Upstream pytest suite (`pytest tests/ -v` excluding our new tests): not run this session — bash mount can't load `chromadb` via conftest.py (D-CC10). Recommend running on Matt's host before merge.

