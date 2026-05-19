# MemPalace Continuous Capture & Productivity Intelligence — Architecture v1.0

**Status:** DRAFT — awaiting Matt's ratification (gate D-CC4 in TCL)
**Date:** 2026-05-19
**Author:** Claude (Cowork session) — derived from `Cowork_Build_Kickoff_Prompt_v1.0`
**Branch:** `feature/mempalace-continuous-capture`
**Supersedes:** *no prior version — the kickoff prompt was the only spec source*

> **Why this exists:** the kickoff prompt declares a v1.0 architecture as a companion document required in-session, but no such file existed on disk. This document is the derived spec: it locks the design shape, makes the kickoff's implicit choices explicit, and surfaces every decision Matt needs to ratify before Phase 1 code begins. Phase 2 and Phase 3 are deliberately under-specified here — a v1.1 spec increment will add depth when those phases start. The goal of v1.0 is to unblock Phase 1, not to over-engineer the rest.

---

## 1. Goal & Success Criteria (carried from kickoff)

Three outcomes define "built":

1. **The six-day diary gap is impossible.** No matter how a session ends (idle, beforeunload, OS kill, network drop, MCP disconnect), at least one Layer 1 path closes the session with a diary entry.
2. **Compaction never destroys context.** The Layer 2 Sentinel writes at least once before every actual compaction event, and tightens its thresholds over time.
3. **The Coaching Agent surfaces at least one actionable insight per week that Matt finds useful** (measured by engagement: open + reply + act-upon).

Two non-goals: this build does NOT replace the existing kg-scheduler diary, and does NOT duplicate session content into MemPalace meta-tables.

---

## 2. System Overview — Four Layers

```
                        ┌──────────────────────────────────────┐
                        │       Claude session activity        │
                        │  (Cowork, Code, Chat-via-MCP, etc.)  │
                        └──────────────────┬───────────────────┘
                                           │ tool calls + idle gaps + page-unload
                                           ▼
        ┌──────────────────────────────────────────────────────────────┐
        │              LAYER 1 — Session-end Auto-Capture              │
        │  ┌────────────┐   ┌────────────────┐   ┌──────────────────┐  │
        │  │   1A       │   │      1B        │   │       1C         │  │
        │  │ Idle 10min │   │ beforeunload   │   │ Heartbeat (3-2-5)│  │
        │  │  timeout   │   │  + sendBeacon  │   │  + dead detect   │  │
        │  └─────┬──────┘   └────────┬───────┘   └────────┬─────────┘  │
        │        └──────────┬────────┴────────────────────┘            │
        └───────────────────┼───────────────────────────────────────────┘
                            │ converged dedupe gate
                            ▼
        ┌──────────────────────────────────────────────────────────────┐
        │             LAYER 2 — Compaction Sentinel                    │
        │  Token-aware adaptive write thresholds (80/90/92/94/96/98%)  │
        │  Per-thread baseline learning after 3 compaction events      │
        └───────────────────────────┬──────────────────────────────────┘
                                    │
                                    ▼
        ┌──────────────────────────────────────────────────────────────┐
        │       LAYER 0 — MemPalace (existing, source of truth)        │
        │     wing_productivity-intelligence (compaction-tuning,       │
        │                  heartbeat-tuning rooms)                     │
        └───────────────────────────┬──────────────────────────────────┘
                                    │ reads only (no writebacks except own meta)
                                    ▼
        ┌──────────────────────────────────────────────────────────────┐
        │              LAYER 3 — Agent Team (six agents)               │
        │  Heartbeat Optimizer · Pattern Analyst · KG Curator          │
        │  Themed Comparator · Growth Trajectory · Coaching Agent      │
        └──────────────────────────────────────────────────────────────┘
```

**Hard rules carried from kickoff §Hard Constraints:**
- MemPalace is the source of truth. Agents read; they do not duplicate.
- Tech stack is locked. No new database. No Supabase. SQLite-in-fork preferred for operational state (see §6).
- Atlas UI/UX Governance V1.1 applies to any user-facing dashboard (Phase 5).
- Atlas Database Agent Governance applies to any agent with 50+ persistent records (most Layer 3 agents).
- Atlas Development Delivery Standard V1.1 applies (TCL present, pre-push review mandatory).
- Versioning is mandatory at every deliverable, schema migration, and agent.

---

## 3. Layer 0 — MemPalace Data Setup

**Action (Phase 0.5 / v0.1.0.4):** register a new wing via MemPalace MCP:

| Wing | Rooms | Purpose |
|---|---|---|
| `wing_productivity-intelligence` | `compaction-tuning` | Sentinel learning history — every threshold adjustment with reasoning |
| | `heartbeat-tuning` | Heartbeat Optimizer learning — pulse-cadence adjustments with evidence |

**What does NOT go in MemPalace:**
- Session diary entries (those go in `wing_claude` per Recovery-Pass-v1.0).
- Operational state (idle timers, heartbeats, queues) — those live in the new SQLite (§6).
- Agent outputs (insights, comparator results) — those are cached, not memorialized.

**Why only those two rooms:** per kickoff §Hard Constraint #1, the only meta-data the system writes to MemPalace is about its own learning. Compaction thresholds and heartbeat curves are the only things that learn. The other Layer 3 agents read but don't write to MemPalace.

---

## 4. Layer 1 — Session-end Auto-Capture (Phase 1 build target)

### 4.1 Activity model — pragmatic interpretation (resolves D-CC2)

The kickoff's "Frontend: Track user activity events (keypress, click, scroll, message send) per thread" cannot be implemented literally — Matt does not control Cowork's frontend, Claude Code's frontend, or claude.ai's frontend.

**The activity surface is the MCP protocol itself.** Every Claude session that has the MemPalace MCP connected emits tool calls (`mempalace_status`, `mempalace_search`, `mempalace_add_drawer`, `mempalace_kg_query`, etc.) as Claude works. The MemPalace MCP server can treat every authenticated tool call as an implicit activity pulse for that session token / thread id. No client-side instrumentation needed.

**Concretely:**
- Each MCP tool call carries the session's bearer token. The token is the **session identity**.
- A timestamp is recorded against that token on every tool call: `last_activity[token] = now()`.
- The "thread" is the longest contiguous run of activity for a token before a 10-minute silence.

**Trade-off:** sessions that connect MemPalace but never call a tool would not register any activity. **Mitigation:** Layer 1B/1C cover those cases — the heartbeat is an explicit liveness pulse independent of tool calls, and `beforeunload` fires from any Atrium-connected page even without a tool call.

**Decision required from Matt (D-CC2):** ratify this server-side activity model, OR direct me to implement a different host. Default below assumes ratification.

### 4.2 Layer 1A — Idle 10-minute timeout

**Trigger:** No MCP tool call observed for any session token in the last 10 minutes.

**Action:**
1. Server marks the token's session as `idle_closed`.
2. Server fetches the message context for that thread from Anthropic API (`messages.list` with the thread_id stored in the session table).
3. Server formats an AAAK diary entry from the message context.
4. Server calls `mempalace_diary_write` (existing tool — verify signature in Phase 0.4) with the AAAK entry.
5. On success, record `diary_written_at` in `idle_session` table.
6. On failure, queue for retry (max 3 retries, exponential backoff: 30s, 5min, 30min).

**Data shape — new table `idle_session`** (SQLite, see §6):

```sql
CREATE TABLE idle_session (
    token              TEXT PRIMARY KEY,          -- bearer token hash, not the token itself
    first_activity_at  TIMESTAMP NOT NULL,
    last_activity_at   TIMESTAMP NOT NULL,
    thread_id          TEXT,                       -- Anthropic API thread id, if discoverable
    last_message_id    TEXT,
    status             TEXT NOT NULL DEFAULT 'active', -- active | idle_closed | diary_written | failed
    diary_written_at   TIMESTAMP,
    diary_drawer_id    TEXT,                       -- the resulting drawer ID
    retry_count        INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT,
    created_at         TIMESTAMP NOT NULL DEFAULT (datetime('now')),
    updated_at         TIMESTAMP NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_idle_session_status_last_activity ON idle_session(status, last_activity_at);
```

**Endpoint contract — NEW** `POST /api/mempalace/diary-write`:

The kickoff places this on the "backend" side. The pragmatic interpretation: the MemPalace HTTP wrapper already has `/mcp` and `/health` (per Phase 2 v0.2). Add an internal `/api/mempalace/diary-write` that only the idle-sweeper / beacon receiver / heartbeat dead-detector call.

```http
POST /api/mempalace/diary-write
Authorization: Bearer <wrapper-internal-token>
Content-Type: application/json

{
  "token_hash": "sha256:...",
  "trigger": "idle_10min" | "beforeunload" | "heartbeat_dead",
  "thread_id": "optional - if known",
  "last_message_id": "optional",
  "fallback_summary": "optional - free text from sendBeacon when API unreachable"
}

→ 200 OK   { "drawer_id": "diary_wing_claude_...", "trigger_handled": "idle_10min" }
→ 202 Acc  { "queued": true, "retry_in_s": 30 }
→ 409 Cnf  { "already_written": true, "drawer_id": "diary_wing_claude_..." }
→ 5xx     { "error": "...", "queued": true }
```

**Idle sweeper** (Phase 1A automation): a process that periodically (every 60s) queries `WHERE status='active' AND last_activity_at < now() - INTERVAL '10 minutes'` and triggers `/api/mempalace/diary-write` for each. Implementation: see §10 (Automations).

### 4.3 Layer 1B — beforeunload + sendBeacon

**Trigger:** an Atrium-hosted page (or any future MemPalace-aware page) fires `pagehide` or `beforeunload`.

**Client side** (Atrium JS, new file `static/atrium/js/05-session-beacon.js` — note V1.1 numeric prefix + plain JS):

```javascript
const { useEffect } = React;
function useSessionBeacon(token, threadId, lastMessageId) {
  useEffect(() => {
    const payload = JSON.stringify({
      token_hash: token,  // already SHA-256 hashed client side
      trigger: 'beforeunload',
      thread_id: threadId,
      last_message_id: lastMessageId,
      timestamp: Date.now()
    });
    const send = () => navigator.sendBeacon('/api/mempalace/beacon', payload);
    window.addEventListener('pagehide', send);
    window.addEventListener('beforeunload', send);
    return () => {
      window.removeEventListener('pagehide', send);
      window.removeEventListener('beforeunload', send);
    };
  }, [token, threadId, lastMessageId]);
}
```

**Server side — NEW** `POST /api/mempalace/beacon` (accepts text/plain because sendBeacon ignores content-type):

```http
POST /api/mempalace/beacon
Content-Type: text/plain

{ "token_hash":"...", "trigger":"beforeunload", "thread_id":"...", "last_message_id":"...", "timestamp": 1747000000000 }

→ 204 No Content (always — beacon receivers must be terse and fast)
```

The endpoint enqueues a row in `diary_write_queue` and returns immediately. An async worker (see §10) drains the queue.

**Data shape — new table `diary_write_queue`:**

```sql
CREATE TABLE diary_write_queue (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash         TEXT NOT NULL,
    trigger            TEXT NOT NULL,             -- idle_10min | beforeunload | heartbeat_dead
    thread_id          TEXT,
    last_message_id    TEXT,
    received_at        TIMESTAMP NOT NULL,
    processed_at       TIMESTAMP,
    drawer_id          TEXT,                       -- set on success
    retry_count        INTEGER NOT NULL DEFAULT 0,
    last_error         TEXT,
    UNIQUE(token_hash, thread_id, trigger, received_at)
);
CREATE INDEX idx_dwq_unprocessed ON diary_write_queue(processed_at) WHERE processed_at IS NULL;
```

**Dedup behavior:** if Layer 1A and Layer 1B both fire for the same `(token_hash, thread_id)` within 5 minutes, the second arrival hits the `UNIQUE` constraint or — more cleanly — the worker checks for an existing `drawer_id` on the same session/thread before writing a new one. **No duplicate diary entries.**

### 4.4 Layer 1C — Heartbeat with adaptive curve

**Pulse endpoint — NEW** `POST /api/mempalace/heartbeat`:

```http
POST /api/mempalace/heartbeat
Authorization: Bearer <session-bearer>
Content-Type: application/json

{ "token_hash":"...", "thread_id":"...", "last_message_id":"...", "user_state":"active|typing|idle" }

→ 200 OK { "next_interval_s": 180 }   ← server tells client when to pulse next
```

**Cadence curve** (initial values; Heartbeat Optimizer will refine):

| Session age | Interval |
|---|---|
| 0–3 min | 180s (3 min) |
| 3–15 min | 300s (5 min) |
| 15+ min | 120s (2 min) — assumption is that long sessions have more state to lose, so we pulse more often |

The cadence is **negotiated by the server**, not hard-coded in the client. The client just respects `next_interval_s`. This is what lets the Heartbeat Optimizer adjust over time without redeploying the client.

**Data shape — new table `heartbeat`:**

```sql
CREATE TABLE heartbeat (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash          TEXT NOT NULL,
    thread_id           TEXT,
    pulse_at            TIMESTAMP NOT NULL,
    last_message_id     TEXT,
    user_state          TEXT,                      -- active | typing | idle
    session_age_at_pulse_s  INTEGER NOT NULL,
    next_interval_s     INTEGER NOT NULL,          -- what we told the client
    state_changed       BOOLEAN NOT NULL DEFAULT 0 -- did user_state differ from previous pulse?
);
CREATE INDEX idx_hb_token_pulse ON heartbeat(token_hash, pulse_at);
```

**Dead-thread detector** (Phase 1C automation): every 30s, query `SELECT token_hash, MAX(pulse_at) AS last_pulse, MAX(next_interval_s) AS expected FROM heartbeat WHERE pulse_at > now() - INTERVAL '1 hour' GROUP BY token_hash HAVING (now() - MAX(pulse_at)) > 2 * MAX(next_interval_s)`. For each result, trigger `/api/mempalace/diary-write` with `trigger='heartbeat_dead'`.

**Why 2× the current interval:** one missed pulse could be a network blip. Two consecutive missed pulses is a high-confidence signal that the session is gone.

### 4.5 Layer 1 — Convergence & dedupe

All three Layer 1 paths funnel into the same `/api/mempalace/diary-write` endpoint via `diary_write_queue`. The single point of dedup is: **does any drawer already exist tagged with this `(token_hash, thread_id)`?** If yes, return 409. If no, write.

This guarantees the success criterion: every session closes with exactly one diary entry, regardless of which Layer 1 path got there first.

---

## 5. Layer 2 — Compaction Sentinel (Phase 2 — spec stub)

**Will be fleshed out in v1.1 of this document.** For Phase 1 scope, just the contract:

- Sentinel observes per-thread token consumption via Anthropic usage API.
- Initial fixed write thresholds: 80%, 90%, 92%, 94%, 96%, 98% of context fill.
- After 3 compaction events on a thread, run a tuning analysis — what thresholds actually triggered before compaction? Adjust per-thread baseline.
- Tuning log: append to MemPalace `wing_productivity-intelligence/compaction-tuning` room as a drawer per adjustment.

**Phase 1 does not build Layer 2.** No tables, no endpoints. The mention here is so Phase 1's schema doesn't accidentally collide.

---

## 6. Persistence Model — Resolves D-CC1

Per kickoff: "Tech stack is locked. No new database. Postgres via SQLAlchemy/Alembic."

But the kickoff also targets `mempalace-fork`, not Atlas. The fork's persistence model is **ChromaDB for memory content + SQLite for KG/operational state** (see `mempalace/palace_graph.py`). Adding Postgres to mempalace-fork would violate the "no new database" rule for THIS repo.

**Decision:** Layer 1 operational state goes in a **new SQLite database** at `~/.mempalace/continuous_capture.db`. Schema is owned by this build. Migrations via a lightweight Python migrator (NOT Alembic — Alembic is Atlas territory).

**Three tables, all from §4 above:**
- `idle_session`
- `diary_write_queue`
- `heartbeat`

**Why SQLite:**
1. Matches existing mempalace-fork pattern (palace_graph.py is sqlite).
2. Self-contained — Phase 0.4 doesn't need to verify a Postgres connection.
3. The volume is bounded — ~1 row per session per minute heartbeat + ~1 row per session per close. Even at 100 sessions/day, that's ~10k rows/day on the heartbeat table; a TTL sweep keeps it small.
4. Single-writer container model (per Phase 2 v0.2 §A4) means no concurrency drama.

**Decision required from Matt (D-CC1 revised):** ratify SQLite-in-fork, OR direct me to use Atlas Postgres (which would mean dual-repo work and a separate Alembic migration).

---

## 7. Auth Model

Two endpoint classes:

**Public-ish (bearer-protected):** `/api/mempalace/heartbeat`. Authenticated by the session's bearer token, same as `/mcp`. The token's hash is what we store.

**Internal (wrapper-token-protected):** `/api/mempalace/diary-write`. Only called by the sweeper, the beacon worker, and the dead-detector — all server-side, all in-container. A separate `INTERNAL_API_TOKEN` env var gates this. Never exposed to clients.

**Open (no auth):** `/api/mempalace/beacon`. `navigator.sendBeacon()` cannot set Authorization headers. Token identity is in the payload as `token_hash`. Worst case: an unauthenticated attacker can enqueue a beacon for any token_hash they know, causing a duplicate diary-write attempt — which the dedup gate already handles. Acceptable.

---

## 8. Failure Handling

**The fundamental failure mode this build addresses:** Recovery-Pass-v1.0 found *"Diary write — BLOCKED. The MemPalace MCP connector isn't loaded in this Cowork session."* If the new endpoints rely on the same MCP connector that fails to load, the build is no better than today.

**Mitigation:** the Layer 1 endpoints DO NOT depend on the MCP connector being loaded in the CLIENT session. They run server-side on the HTTP wrapper container, with `mempalace_diary_write` called as a Python function (in-process) rather than over MCP. The container's wrapper holds the subprocess to mempalace, so we always have an in-process callable.

**Retry policy:**
- Network failure to Anthropic API: 3 retries with exponential backoff (30s, 5min, 30min).
- MemPalace write failure: 3 retries with same policy.
- After 3 retries: mark `diary_write_queue` row as `status=failed` with `last_error` set. Daily report surfaces failed rows to Coaching Agent for alerting.

**Container restart:** SQLite tables survive restart (volume-mounted per Phase 2 v0.2). Any in-flight beacon-receiver requests during a restart are lost (acceptable — Layer 1A's idle sweeper picks them up within 60s anyway).

---

## 9. Open Decisions for Matt's ratification

These MUST be answered before Phase 1A code begins:

| ID | Decision | Default | Why it blocks Phase 1 |
|---|---|---|---|
| **D-CC1** | Operational state DB choice | **SQLite at `~/.mempalace/continuous_capture.db`** (§6) | Phase 1A schema migration depends on it |
| **D-CC2** | Activity surface (server-side MCP vs client-side) | **Server-side via MCP tool calls** (§4.1) | Phase 1A endpoint design depends on it |
| **D-CC3** | API key env var name | **`ANTHROPIC_API_KEY` canonical**, `CLAUDE_API_KEY` deprecated | Phase 0.4 + Phase 1A Anthropic-API client init |
| **D-CC4** | Spec v1.0 ratification | — (THIS document) | Phase 1A coding gate |
| **D-CC5** | CRLF/LF working-tree drift | **Always `git add <file>`, never `git add .` on this branch** | Avoid 37k-line bogus diff at commit time |
| **D-CC6** | Test gate | **build-tester (Light Test) per phase + `pytest tests/ -v`** | Phase 1A.5 gate definition |
| **D-CC7** | Auth on `/api/mempalace/beacon` | **No auth — token in payload, dedup is the guard** (§7) | Phase 1B endpoint contract |
| **D-CC8** | Initial heartbeat curve values | **180s / 300s / 120s per kickoff** (§4.4) | Phase 1C client default |

A "yes / proceed with defaults" reply from Matt clears all 8 in one shot. If any need changes, mention the ID + new value and the spec gets a v1.1 with the override locked.

---

## 10. Automations (kickoff Category 8)

Three new automations introduced by Phase 1:

| Name | Trigger | Action | Implementation |
|---|---|---|---|
| `idle_sweeper` | every 60s | Find sessions idle > 10min, POST to /diary-write | asyncio task in the wrapper (NOT node-cron — this is the Python wrapper container) |
| `beacon_worker` | every 5s (queue-driven) | Drain `diary_write_queue` rows, POST to /diary-write | asyncio task in the wrapper |
| `dead_thread_detector` | every 30s | Find token_hashes with missed-pulse > 2× interval, POST to /diary-write | asyncio task in the wrapper |

**Kickoff says "node-cron"** but the wrapper container is Python/Starlette (per Phase 2 v0.2 §A3). `node-cron` would mean adding a Node.js runtime to the container, which conflicts with single-worker pattern (§A4). The substitute: **asyncio tasks managed by the wrapper's lifespan handler**, started on container boot and gracefully cancelled on shutdown.

---

## 11. References

- Cowork Build Kickoff Prompt v1.0 (pasted in this session — no on-disk file)
- `MemPalace_Phase_2_Architecture_v0.2.md` (existing — defines wrapper, container, auth, tunnel)
- `MemPalace_Recovery_Pass_v1.0_Report.md` (existing — establishes the failure mode this build addresses)
- `mempalace/http_server.py` (existing — Starlette wrapper to extend)
- `mempalace/palace_graph.py` (existing — sqlite precedent for §6)
- Atlas Development Delivery Standard V1.1 (governance)
- TECHNICAL_CHANGELOG.md (this branch — live build log)

---

## Version history

- **v1.0 (2026-05-19)** — Initial derivation from kickoff prompt. Phase 1 fully specified; Phase 2/3 stubbed. 8 Open Decisions surfaced for ratification.
