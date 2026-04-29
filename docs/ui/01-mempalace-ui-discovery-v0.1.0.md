# Atrium — MemPalace Visualization Layer · Phase 0 Discovery (v0.1.1)

| Field | Value |
|---|---|
| Document | Atrium (MemPalace Visualization Layer) — Discovery |
| Tool name | **Atrium** (locked v0.1.1 per Matt) |
| Version | v0.1.1 |
| Supersedes | v0.1.0 (in-file stamp; filename retained per convention) |
| Date | 2026-04-28 |
| Author | Claude (Cowork session, on behalf of Matt) |
| Working tree | `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\` |
| Companion | `02-mempalace-ui-prd-v0.1.0.md` (in-file v0.1.1), `03-mempalace-ui-mockups-v0.1.0.md` (in-file v0.1.1), `Claude Workspace\Claude Projects\Governance Documents\Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` |
| Status | Read-only inventory. No code, no schema, no auth changes proposed in this doc. |

> **v0.1.1 changelog (this doc).** (1) Tool name locked: **Atrium** (replaces "MemPalace UI" / "the UI" / "[NAME]" throughout). (2) §G Open Question #1 (naming) resolved → struck. (3) §G Open Question #2 (agent activity ledger) resolved → formal `agent_runs`/`agent_suggestions`/`agent_reviews` schema pulled forward into v0.1.0 of Atrium and specified in the new shared `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`. (4) §G Open Question #4 (CF Access) resolved → CF Access service-auth + email-OTP on `claude-brain.tstly.dev` is a **hard pre-ship gate** for Atrium, not a v0.2.0 task.
>
> Versioning: every entry below is anchored at v0.1.1. Findings that need re-confirmation
> when missing governance docs (UI/UX v1.5, AI Agentic v2.2, API Documentation v0.1.0) land
> are flagged inline as **[v0.1.2 backfill]** (was [v0.1.1 backfill] in the v0.1.0 stamp).

---

## Purpose

The fork ships **no visual UI** today (confirmed by v1.15 deployment log, "UI-question reconnaissance"). The only interfaces to the palace are (a) the `mempalace` CLI on Matt's laptop, (b) the 19 `mempalace_*` MCP tools surfaced inside any connected Anthropic client (claude.ai, Cowork, Claude Desktop, Claude Code), and (c) the `.claude-plugin` / `.codex-plugin` slash-commands.

This Phase 0 doc inventories *what already exists in the fork* so Phase 1 (the PRD) can scope a visualization layer on top — without inventing data structures or auth surfaces that the palace doesn't actually have.


---

## Section A — Data Model Inventory

### A.1 Drawers (ChromaDB collection `mempalace_drawers`)

The verbatim store. Every fact, snippet, and conversation chunk that ever lands in the palace is one *drawer*. Persisted in a single ChromaDB `PersistentClient` collection at `palace_path` (default `~/.mempalace/palace`, in-container `/data/.mempalace/palace`).

| Field | Type | Source |
|---|---|---|
| `id` | str | `drawer_{wing}_{room}_{sha256[:24]}` — deterministic on `wing+room+content[:100]` (`mempalace/mcp_server.py` `tool_add_drawer`). |
| `documents` | str | The verbatim chunk. Never summarized. Bounded at 100 KB by `sanitize_content`. |
| `metadatas` | dict | `wing`, `room`, `hall`, `source_file`, `chunk_index`, `added_by`, `filed_at` (ISO), and on diary entries also `topic`, `type=diary_entry`, `agent`, `date`. |

The deterministic ID makes `add_drawer` idempotent — replays return `already_exists` rather than dupe (`mcp_server.py` lines ~330-345).

### A.2 Wings — top-level domains

Set per-deployment in the bootstrap identity. The hosted palace's identity (`http_server.py` `IDENTITY_TEXT`, ~95 tokens, "D9 Draft C, locked") declares **four wings**:

- `wing_mega` — corporate (Mega Entertainment parent)
- `wing_iep` — events ops (Interactive Event Productions)
- `wing_atlas` — software / dev
- `wing_personal`

Plus per-agent diary wings (`wing_<agent_name_lower>`, see A.7). The default upstream wings list lives in `mempalace/config.py` `DEFAULT_TOPIC_WINGS` (events, venues, vendors, timelines, budgets, team, clients, productions, equipment, creative, technical) — but the IEP fork's identity overrides that list.

### A.3 Halls — 12 cross-cutting categories

Common to every wing per the locked identity:

> events, venues, vendors, timelines, budgets, team, clients, productions, equipment, creative, technical, **and the always-present diary**.

Halls are stored in drawer metadata as `hall=hall_<name>` (e.g. `hall_diary`). Hall keyword maps for the auto-classifier live in `config.py` `DEFAULT_HALL_KEYWORDS`.

### A.4 Rooms — named ideas

Hyphenated slugs (e.g. `gala-2026-spring`, `chromadb-setup`). Stored as `metadata.room`. A room may appear in multiple wings — when it does, that's a **tunnel** (see A.6). Names sanitized by `config.py::sanitize_name` (max 128 chars, no `..`, no `/\\`, no nulls, restricted character set).

### A.5 Knowledge Graph (SQLite)

Path: `<palace_path>/knowledge_graph.sqlite3` (or default `~/.mempalace/knowledge_graph.sqlite3`). Schema in `mempalace/knowledge_graph.py` `_init_db`:

```
entities(id PK, name, type, properties JSON, created_at)
triples (id PK, subject FK, predicate, object FK,
         valid_from, valid_to, confidence, source_closet,
         source_file, extracted_at)
```

This is the temporal entity-relationship graph (subject → predicate → object with `valid_from`/`valid_to` dates). It's what competes with Zep's temporal KG. Indexes on subject, object, predicate, valid range. Auto-creates entities on `add_triple`. Invalidation sets `valid_to`. WAL journal mode.

### A.6 Palace Graph (derived, not stored)

`mempalace/palace_graph.py` builds a graph **on the fly** from ChromaDB metadata at query time:

- **Nodes** = rooms with `{wings: set, halls: set, count, dates}`.
- **Edges** = "tunnels" — same room name appearing in 2+ wings.

Three operations: `traverse(start_room, max_hops)`, `find_tunnels(wing_a, wing_b)`, `graph_stats()`. There is **no persistent graph store**; every call rebuilds from a paginated `col.get(limit=1000, offset=...)` sweep of metadata.

### A.7 Diary — per-agent wing

Each agent gets its own wing `wing_<agent_name_lower>` with a single `diary` room and `hall_diary` hall. Entries are AAAK-compressed (per `mcp_server.py` `AAAK_SPEC`). `tool_diary_write` and `tool_diary_read` are the only tools that touch them. Entry IDs follow `diary_<wing>_<YYYYMMDD_HHMMSS>_<sha256[:12]>`.

### A.8 Write-Ahead Log (WAL) — **the agent activity ledger that already exists**

`mempalace/mcp_server.py::_wal_log` writes a JSON line to `~/.mempalace/wal/write_log.jsonl` for every write operation:

```
{timestamp, operation, params, result}
```

Operations logged: `add_drawer`, `delete_drawer`, `kg_add`, `kg_invalidate`, `diary_write`. Permissions hardened (`0o700` dir, `0o600` file). This is the closest thing the fork has to an agent-activity ledger — see Section C for what it does and does not give the UI.

### A.9 Configuration & state

| Path | Owner | Purpose |
|---|---|---|
| `~/.mempalace/config.json` | `MempalaceConfig` | `palace_path`, `collection_name`, `topic_wings`, `hall_keywords` |
| `~/.mempalace/people_map.json` | `MempalaceConfig` | name-variant → canonical-name map |
| `~/.mempalace/identity.txt` | bootstrap | L0 identity layer (D9 Draft C); written first-boot if absent |
| `~/.mempalace/wal/write_log.jsonl` | mcp_server | audit trail (A.8) |
| `<palace_path>/` | ChromaDB | drawers + embeddings |
| `<palace_path>/knowledge_graph.sqlite3` | KG | entities + triples |

In the hosted container, `HOME=/data` (per Hardening Fix #14), so all of the above sit under `/data/.mempalace/`.


---

## Section B — MCP Tool Inventory (19 tools)

All tools defined in `mempalace/mcp_server.py` `TOOLS` dict and surfaced via `tools/list` over the JSON-RPC `/mcp` endpoint. Read tools are safe to back the UI's read paths; write tools should remain the only mutation surface (see PRD architecture decision).

| # | Tool | Kind | Returns | One-line description |
|---|---|---|---|---|
| 1 | `mempalace_status` | read | `{total_drawers, wings, rooms, palace_path, protocol, aaak_dialect}` | Palace overview + the wake-up protocol + AAAK spec. Also the on-boot teach payload. |
| 2 | `mempalace_list_wings` | read | `{wings: {name: count}}` | All wings with drawer counts. |
| 3 | `mempalace_list_rooms` | read | `{wing, rooms: {name: count}}` | Rooms inside a wing (or all rooms if no wing). |
| 4 | `mempalace_get_taxonomy` | read | `{taxonomy: {wing: {room: count}}}` | Full wing → room → drawer-count tree. |
| 5 | `mempalace_get_aaak_spec` | read | `{aaak_spec}` | The AAAK compressed-memory dialect spec. |
| 6 | `mempalace_kg_query` | read | `{entity, as_of, facts, count}` | Facts about an entity, with optional `as_of` time travel and direction filter. |
| 7 | `mempalace_kg_add` | write (KG) | `{success, triple_id, fact}` | Add a `subject → predicate → object` triple with optional `valid_from`. |
| 8 | `mempalace_kg_invalidate` | write (KG) | `{success, fact, ended}` | Set `valid_to` on a triple — fact is no longer current. |
| 9 | `mempalace_kg_timeline` | read | `{entity, timeline, count}` | Chronological story of an entity (or all). |
| 10 | `mempalace_kg_stats` | read | `{entities, triples, current_vs_expired, predicates}` | KG overview. |
| 11 | `mempalace_traverse` | read | `[{room, wings, halls, count, hop, connected_via}]` | BFS walk from a start room, capped at `max_hops`. |
| 12 | `mempalace_find_tunnels` | read | `[{room, wings, halls, count, recent}]` | Rooms that bridge ≥2 wings, optionally filtered by `wing_a`/`wing_b`. |
| 13 | `mempalace_graph_stats` | read | counts + connectivity | Palace-graph overview: nodes, tunnels, edges, wing distribution. |
| 14 | `mempalace_search` | read | `{results: [{document, metadata, similarity}], _sanitization}` | Semantic search via Chroma `query`, with prompt-injection sanitizer. |
| 15 | `mempalace_check_duplicate` | read | `{is_duplicate, matches: [{id, wing, room, similarity, content}]}` | Pre-flight dupe check before filing. |
| 16 | `mempalace_add_drawer` | write | `{success, drawer_id, wing, room}` | File verbatim content into wing/room. Idempotent on deterministic ID. |
| 17 | `mempalace_delete_drawer` | write | `{success, drawer_id}` | Delete by ID. WAL-logged with content-preview for audit. |
| 18 | `mempalace_diary_write` | write | `{success, entry_id, agent, topic, timestamp}` | Append AAAK diary entry to the agent's `wing_<name>/diary` room. |
| 19 | `mempalace_diary_read` | read | `{agent, entries[], total, showing}` | Last N diary entries for an agent, newest-first. |

Counts: **13 read tools + 6 write tools = 19**, matching the smoke-test in v1.14 ("`/mcp with OAuth JWT → 200, 19 mempalace_* tools`").

JSON-RPC envelope: `tools/list`, `tools/call`. Rate-limited at 60 req/min per process via the in-process `RateLimiter` token-bucket (`mcp_server.py` lines ~46-86).

---

## Section C — Agent Surfaces & the Activity-Ledger Gap

Matt's framing for **Atrium**: *"Status, current work, suggestions, reviews, in real time, and interact with them — approve / decline / edit suggestions."* The fork's current shape:

### What exists today

| Surface | Location | What it gives the UI |
|---|---|---|
| **Write-Ahead Log** (A.8) | `~/.mempalace/wal/write_log.jsonl` | A chronological JSONL ledger of every write. Has `timestamp`, `operation`, `params`, `result`. **Sufficient for an "Agent Activity Feed"**. |
| **Per-agent diary** (A.7) | drawers in `wing_<agent>/diary` | Free-form AAAK journal entries. Sufficient for an "agent-says" panel. |
| **Mining runs** | `mempalace/miner.py` (project-files), `mempalace/convo_miner.py` (chat exports) | Both are **CLI invocations** (`mempalace mine ...`). They print to stderr/stdout and write drawers via the palace; they do **not** emit a structured run record. |
| **The 19 MCP tools' invocation history** | not persisted | Read tools leave no trace. Write tools leave a WAL line per call. |

### What is **missing** for Atrium as Matt described it

The fork has no formal concept of:

1. **Agent run** — a unit of work with `run_id`, `agent_name`, `started_at`, `ended_at`, `status` (`running`/`completed`/`failed`), and a *narrative* of what it did.
2. **Suggestion** — a proposed write that's pending Matt/Luke approval. There is no "draft drawer" or "draft triple" state. Today, `add_drawer` / `kg_add` write straight through.
3. **Review** — a completed audit pass over a drawer, fact, or run, with a verdict (`approve` / `decline` / `edit`) and the reviewer.
4. **Mining-run record** — what was mined, how many drawers were filed, how many were duplicates, how long it took.

> **Gap 1 — `agent_runs` table.** Phase 1 PRD will need to specify either (a) a new SQLite/Postgres table next to the KG, or (b) extending the WAL schema with `run_id` and `agent_name`, or (c) leaving runs out of v0.1.0 and only showing the WAL feed.
>
> **Gap 2 — `agent_suggestions` queue.** Either a new table, or a soft-delete pattern on drawers/triples (`status: pending|approved|rejected`), or a separate "inbox" wing (e.g. `wing_inbox/<agent_name>`) that Atrium surfaces and Matt promotes by re-filing into the canonical wing.
>
> **Gap 3 — `agent_reviews` log.** Probably the same surface as Gap 2's resolution.

These gaps were flagged here in v0.1.0 with the v0.1.0 PRD scope assuming the simplest answer (read the existing WAL + diary, defer formal runs/suggestions/reviews to v0.2.0+).
**v0.1.1 update — Matt reversed the deferral.** All three gaps are filled in v0.1.0 of Atrium by adopting the formal `agent_runs` / `agent_suggestions` / `agent_reviews` schema specified in `Claude Workspace\Claude Projects\Governance Documents\Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`. The schema is co-designed with the upcoming Atlas project-track tool and lives in **Atlas Postgres** (not MemPalace's Path-C Postgres) so that agent activity sits next to the rest of Atlas's operational governance. See PRD §6.6 for how Atrium reads/writes the ledger.


---

## Section D — HTTP Surface Inventory

Source: `mempalace/http_server.py` `create_app` route table.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness — wrapper alive. Does NOT round-trip to the stdio MCP subprocess (ChromaDB ONNX cold start can take 30s). |
| GET | `/ready` | none | Readiness — `proxy.healthcheck()` round-trips an `initialize` JSON-RPC to the subprocess. 200 `ready` or 503 `subprocess unhealthy`. |
| GET | `/authorize` | none (OAuth) | OAuth 2.1 authorization-code endpoint. Validates `client_id` + `redirect_uri`, mints a 10-min one-time `code`, redirects to `redirect_uri?code=...&state=...`. No user-consent UI (single-user server). |
| POST | `/oauth/token` | none (OAuth) | Token endpoint. Handles **both** `grant_type=authorization_code` (Anthropic Connectors, with PKCE S256) and `grant_type=client_credentials` (legacy/diagnostic). Issues HS256 JWT, default 1h TTL. |
| GET | `/.well-known/oauth-authorization-server` | none | RFC 8414 AS metadata. Advertises `authorization_code` + `client_credentials` and S256. |
| GET | `/.well-known/oauth-protected-resource` | none | RFC 9728 RS metadata. Pointed at by 401 `WWW-Authenticate: Bearer resource_metadata=...`. |
| POST | `/mcp` | **bearer OR OAuth JWT** | The single MCP transport. Accepts a JSON-RPC body, forwards to the long-lived `python -m mempalace.mcp_server` subprocess via `StdioProxy`, returns the response. Single-worker invariant (`uvicorn --workers 1`). |

**Bearer auth.** `MEMPALACE_BEARER_TOKEN` env var, ≥16 chars, `secrets.compare_digest`. Refusal-to-start if unset.

**OAuth.** Three env vars: `MEMPALACE_OAUTH_CLIENT_ID` (32 chars), `MEMPALACE_OAUTH_CLIENT_SECRET` (44 chars), `MEMPALACE_OAUTH_JWT_SECRET` (64 chars). Verified by `oauth.verify_jwt`. In-memory authz-code store (single-process).

**No HTML, no static files, no `/web` / `/admin` / `/ui` / `/library` routes** (confirmed v1.15). No `templates/` or `static/` directory in the repo. **Atrium** (Phase 1) lands here.

---

## Section E — Auth & Cloudflare Access

### What's actually plumbed (verified against deployment logs v1.10–v1.15)

- **Cloudflare Tunnel.** Public hostname `claude-brain.tstly.dev` routes to `localhost:5042` on the Coolify host via the existing `atlas-dev` Cloudflare tunnel (v1.13). Tunnel terminates TLS and forwards as plain HTTP to origin (cosmetic 401 `WWW-Authenticate` scheme bug noted in v1.14, non-blocking).
- **Bearer token** (laptop CLI / curl) — `MEMPALACE_BEARER_TOKEN`.
- **OAuth 2.1 authorization_code + PKCE S256** (Anthropic Connectors / Cowork / Claude Desktop / claude.ai web+mobile text mode) — Phase 10 complete (v1.14, 2026-04-27).

### What Matt's task description references — **flagged for confirmation**

Matt's brief says: *"Inventory CF Access policies on `claude-brain.tstly.dev` — service auth + email OTP for matt@/luke@ (verify against the Phase 10 deployment log)."*

The deployment session logs v1.0 through v1.15 do **not** record a Cloudflare Access (Zero Trust) policy ever being attached to `claude-brain.tstly.dev`. The relevant references:

- v1.2 (line ~46) treats CF Access as *optional* future hardening: *"Cloudflare Access or a similar IP/geo guard could optionally be layered on `mempalace.tstly.dev` for an extra ring before Phase 7.5."*
- v1.13–v1.15 describe only CF Tunnel + bearer + OAuth. No Access policy.
- The Atlas **Security Admin Governance v0.1.0** (Section 2 — Threat Model) describes the canonical Atlas pattern as: *"Cloudflare edge | Trusted-with-policy | Applies Service Auth + Email OTP policies."* So the *Atlas* convention is service auth + email OTP — and it would be a sensible policy for `claude-brain.tstly.dev`, but the deployment logs do not show it landed there yet.

> **Discovery finding:** the auth surface today is bearer + OAuth at the Starlette layer. CF Access service-auth + email-OTP for `matt@/luke@` is the **Atlas standard from Security Admin Governance v0.1.0** but **not yet documented as live** on this hostname.
>
> **v0.1.1 update — Matt confirmed not relaxed.** CF Access on `claude-brain.tstly.dev` is a **hard pre-ship gate** for Atrium. PRD §3.3 carries the binding wording and a Pre-ship CF Access checklist; see also `Claude Workspace\mempalace-fork\docs\architecture\03-cf-access-setup-v0.1.0.md` for the operational steps Matt runs at his laptop before Atrium build kicks off.

---

## Section F — Governance Doc Landscape (state at 2026-04-28)

Matt's brief calls for citations against six governance docs at `Claude Workspace\Claude Projects\Governance Documents\`. Actual state on disk:

| Doc Matt referenced | Expected version | On-disk state | Cite as |
|---|---|---|---|
| Master | (Atlas Development Delivery Standard) | `ATLAS_DEVELOPMENT_DELIVERY_STANDARD_V1.1.md` | **V1.1** ✅ |
| UI/UX | v1.5 | `ATLAS_UI_UX_GOVERNANCE_FRAMEWORK_v1.4.md` (newest .md), v1.3 archived as PDF | **v1.4** ⚠️ pending v1.5 — **[v0.1.1 backfill]** |
| AI Agentic | v2.2 | `Reviews\02_ai_agentic_review_v0.1.1.md` only (review of v2.1; v2.2 not yet authored) | **review v0.1.1** ⚠️ — **[v0.1.1 backfill]** |
| Database | v0.1.0 | `ATLAS_DATABASE_GOVERNANCE_FRAMEWORK_v0.1.0.md` | **v0.1.0** ✅ |
| Security Admin | v0.1.0 | `ATLAS_SECURITY_ADMIN_GOVERNANCE_FRAMEWORK_v0.1.0.md` | **v0.1.0** ✅ |
| API Documentation | v0.1.0 | `Reviews\05_api_documentation_review_v0.1.0.md` only (framework draft, not yet a standalone doc) | **review v0.1.0** ⚠️ — **[v0.1.1 backfill]** |

Per Matt's "fail soft" instruction, the PRD cites the latest available artifact for each row and tags the three ⚠️ rows for re-citation in v0.1.1 once the missing frameworks land.

### Most relevant subsections, captured here so the PRD can reference them

- **Atlas Development Delivery Standard V1.1** — 9 categories. Cat 4 (Permissions) governs auth choice; Cat 9 (Frontend Delivery) governs no-bundler / Jinja patterns / JS injection shims; Cat 8 (Automations) governs scheduled-task patterns.
- **UI/UX v1.4** — Sidebar 220–260 px expanded / 60 px collapsed; icon+label rule; standard 8-zone record page layout; status color codes; **canonical dark-mode design tokens** (the `--bg-primary #0c1425`, `--bg-card #162236` / `#1a2a42` gradient palette and the `atlas-card` / `atlas-modal` / `atlas-section-header` CSS hooks); button-in-header rule for popups; inline-editable fields by double-click; inline confirmation strip for destructive actions; light/dark/adaptive default = adaptive.
- **Database Governance v0.1.0** — Migration naming `NNN_verb_entity.sql` (or open `saNN_entity` per pending Matt decision); ENUM-over-bucket-id-FK rule for state columns; multi-instance inventory (Atlas Core, Executive App on Supabase, Vikunja, etc.) — relevant because the UI may add a new SQLite table next to MemPalace's KG and must follow the convention.
- **Security Admin Governance v0.1.0** — Trust-zone table including the **CF edge applies Service Auth + Email OTP policies** line; cross-zone hop rule (each hop is a security event with its own signal).
- **AI Agentic Review v0.1.1** — Documents the canonical skill chain (atlas-delivery-standard → build-tester → code-review-optimizer → atlas-pre-push-review → cowork-git-push → coolify-feature-branch); the **Pause Before Irreversible Action** principle (proposed §2.10); the missing **Cowork-Runtime Governance Agents** class; the **state-persistence outside the sandbox** rule. All three concepts directly inform how the UI's Suggestions Queue and Reviews surfaces should behave.
- **API Documentation Review v0.1.0** — Stub-routes pattern (`/sales-app/api/{resource}/{id}/{action}-html`), Jinja-vs-JS-injection patterns, REST verb conventions. Relevant for the UI's own `/library`, `/agents`, `/search`, `/settings` route shape.

---

## Section G — Open Questions surfaced by Discovery (handed off to PRD)

> **v0.1.1 status update.** Three of the seven questions are resolved by Matt's v0.1.1 directives and struck below. The remaining four carry into the PRD.

1. ~~**Naming for the UI tool.** MemPalace ships unnamed at the UI layer. PRD will propose 3–5 candidates for Matt's pick.~~ **RESOLVED v0.1.1: Atrium.** Locked, no further discussion in v1.
2. ~~**Agent activity ledger** — adopt the existing WAL as the v0.1.0 surface, or design a richer `agent_runs` schema now?~~ **RESOLVED v0.1.1:** formal `agent_runs` / `agent_suggestions` / `agent_reviews` schema pulled forward into v0.1.0 of Atrium. Schema spec: `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`. Lives in Atlas Postgres, shared with the Atlas project-track tool.
3. ~~**Suggestions queue** — soft-delete on existing tables, or a dedicated inbox surface, or defer?~~ **RESOLVED v0.1.1:** formal `agent_suggestions` table per the shared ledger schema. The `wing_inbox` ChromaDB convention is retained as the *content carrier* for the proposed drawer payload, but state (pending / approved / rejected / edited) lives in `agent_suggestions` rows in Atlas Postgres.
4. ~~**Auth** — accept the existing bearer/OAuth surface as-is for v0.1.0, or take the v0.1.0 cycle to add CF Access (Atlas-standard service-auth + email-OTP) on `claude-brain.tstly.dev`?~~ **RESOLVED v0.1.1: CF Access is a hard pre-ship gate for Atrium.** PRD §3.3 carries the binding wording; operational checklist at `docs/architecture/03-cf-access-setup-v0.1.0.md`.
5. **Co-locate Atrium under `claude-brain.tstly.dev` in the same Starlette app, or carve a separate Coolify service** behind the same tunnel? *(open — PRD §3.1 recommends co-locate Option A.)*
6. **Knowledge-graph viz** — D3 / Cytoscape / vis.js for v0.2.0+? *(open — PRD §3.2 recommends Cytoscape.js for v0.2.0+; defer from v0.1.0.)*
7. **Adjacent system** — the upcoming Atlas project-track tool is a sibling tracker over agentic work scoped to Atlas product development. The agent-activity-ledger pattern is now shared (resolved by Q2). Atlas project-track will reference the same `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`. *(boundary doc handoff still open — PRD §10 is the cross-link.)*

End of Discovery v0.1.1.
