# Atrium — PRD (v0.1.2)

| Field | Value |
|---|---|
| Document | Atrium (MemPalace Visualization Layer) — Product Requirements |
| Tool name | **Atrium** (locked v0.1.1 per Matt) |
| Version | v0.1.2 |
| Supersedes | v0.1.1 (in-file stamp; filename retained per convention) → v0.1.0 |
| Date | 2026-04-28 |
| Author | Claude (Cowork session) |
| Working tree | `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\` |
| Companion | `01-mempalace-ui-discovery-v0.1.0.md` (Phase 0, in-file v0.1.1), `03-mempalace-ui-mockups-v0.1.0.md` (Phase 2, in-file v0.1.1), `Claude Workspace\Claude Projects\Governance Documents\Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` (shared ledger schema), `Claude Workspace\mempalace-fork\docs\architecture\03-cf-access-setup-v0.1.0.md` (CF Access setup) |
| Status | Draft for Matt's review. No code. |
| Citations to **v1.5 / v2.2** governance | placeholders — see §Governance |

> **v0.1.2 changelog (this doc).**
> 1. **Q9 (Atlas API readiness / build order) RESOLVED.** Build order is critical-path-serial with parallel tracks: Atlas endpoints are the gating critical path; Atrium UI shell, CF Access setup, and the static read screens (Library / Search / KG placeholder / Settings) run in parallel and meet at integration. Specified in new §12 Build Order.
> 2. **Q10 (Persona registration ceremony) RESOLVED.** Hybrid model: version-controlled YAML in the Atlas repo + bootstrap script on every Atlas deploy + live registry-editor in Atrium and project-track Settings + **block-by-default** for unregistered agents. Specified in new §13 Persona Registration. (Reflected in schema doc v0.1.1 §3.4 + §7 step 2.)
> 3. **Q3 (service-token sharing) RESOLVED — picked the more secure option.** Atrium mints **per-session per-operator Atlas tokens** when a CF Access OTP session is established. The bootstrap service token is used **only** to call `/api/auth/exchange`. §3.3 row 4 rewritten to spec.
>
> **v0.1.1 changelog (carried forward).**
> 1. **Tool name locked: Atrium.** Replaces "MemPalace UI" / "the UI" / "[NAME]" throughout. §8 Naming simplified to a one-line lock — no further discussion in v1.
> 2. **CF Access on `claude-brain.tstly.dev` confirmed as a hard pre-ship gate** (§3.3 binding wording strengthened; new §3.3.1 Pre-ship CF Access checklist added; §9 governance citation reinforced). Atrium MUST NOT ship until the gate is verifiably in front of the hostname.
> 3. **§6.6 rewritten** to use the formal `agent_runs` / `agent_suggestions` / `agent_reviews` schema specified in the shared `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`. The wing_inbox+JSONL pattern is retained only as the *content carrier* for proposed drawer payloads; state is in Atlas Postgres.
> 4. **§10 Adjacent Systems** updated — the Atlas project-track tool now reads/writes the same shared ledger; the v0.2.0 deferral is dropped.
> 5. **§11 Open Questions** trimmed — Q1 (naming), Q2 (auth), Q3 (suggestions inbox model) resolved.
>
> Versioning policy: every functional change made between this PRD and the build sign-off is tagged with a version stamp (`v0.1.0`, `v0.1.1`, ...) so each iteration is a rollback anchor (per Matt's user-preference rule and the AI-Agentic-Review §2.10 "Pause Before Irreversible Action" principle).

---

## 1. Goal

Give Matt a **visible, browsable, and interactive surface for the memory palace and the agents that operate on it.** Today the palace is felt only through MCP tool calls inside chats; v0.1.0 ships **Atrium** — a small server-rendered web UI under `claude-brain.tstly.dev` that lets Matt (and Luke) (a) see what's actually in the palace at a glance — wings, drawers, recent activity, search — and (b) see the agents working on it in real time, with the ability to approve / decline / edit their suggestions instead of waiting for the next chat session. Everything else (knowledge-graph viz, mining-run dashboards, multi-user permissions) lands in v0.2.0+.

---

## 2. Scope

### 2.1 In v0.1.0 (smallest viable surface — Atrium)

The eight screens enumerated in §6, each scoped to read-mostly behavior plus a single mutation surface (the Suggestions Queue). Auth rides the existing tunnel + bearer/OAuth + **CF Access (mandatory pre-ship — see §3.3)**. **The shared agent activity ledger** (`agent_runs` / `agent_suggestions` / `agent_reviews` / `agent_persona_registry` in Atlas Postgres) is in scope for v0.1.0 — Atrium reads and writes via the Atlas REST surface specified in `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` §5. Inside `mempalace-fork`: Jinja templates + a tiny static-asset directory inside the existing Starlette app, plus a thin REST client to Atlas's ledger API.

### 2.2 v0.2.0+ (deferred, sequenced)

| Bucket | Notes |
|---|---|
| Knowledge-graph viz | D3 / Cytoscape / vis.js node-link rendering of `mempalace_kg_*` data. Defer because: (1) requires a real graph layer over the SQLite triples that doesn't exist yet, (2) interactive layout libraries are the heaviest piece of this surface, and (3) Matt's primary use today is drawer browsing, not graph exploration. |
| Mining-run dashboard | Surfaces `mempalace mine` invocations with progress, dupe-rate, dwell time. v0.1.0 logs every mining run as an `agent_runs` row (per the shared ledger), but a dedicated visualization surface lands in v0.2.0+. |
| Suggestions ribbon-API | Programmatic submission of suggestions from outside agents (Slack-bot, scheduled jobs) — already covered by the shared ledger's `POST /api/agent-ledger/suggestions`. v0.2.0 just means surfacing those external-origin suggestions in Atrium UI explicitly. |
| Multi-user RBAC | Today the only readers are Matt and Luke. v0.2.0 adds a third role (e.g. external auditor) and per-row visibility. Atlas RLS already covers the ledger side. |
| Audit / diff viewer | Render WAL + ledger entries against drawer state to show "what changed when". Useful, not urgent. |
| Connector config | UI for Cowork / Claude Code / Claude Desktop connector setup (currently lives in their respective settings panels). |
| Saved searches & alerts | "Tell me when a new drawer hits `wing_iep/clients/acme-events`." |

### 2.3 Explicitly OUT of scope (any version)

- **A bundled SPA build pipeline.** UI/UX Governance Cat 9 (Frontend Delivery) and the canonical Atlas pattern call for server-rendered Jinja + minimal JS. No webpack, no Vite, no Next.js, no Tailwind compiler.
- **Mutating the upstream `mempalace.mcp_server` module.** The fork rule (Phase 2 architecture A2) is "upstream untouched, wrapper owns the new surface." UI changes go in the wrapper or in new modules; never in `mcp_server.py` or `palace.py`.
- **Re-implementing search.** All semantic search routes through `mempalace_search` (Tool #14) and inherits its prompt-injection sanitizer.
- **Direct user-facing writes for drawers / triples.** Mutation flow is: agent files a draft into `wing_inbox` (carrying the proposed payload) AND writes a corresponding `agent_suggestions` row in Atlas Postgres (state = pending) → Atrium shows it as a suggestion (joined view) → Matt approves → server promotes to canonical wing via the MCP tool AND flips `agent_suggestions.state` to approved. Atrium never bypasses the MCP tools for memory-palace mutations, and never bypasses the ledger API for state mutations.

---

## 3. Architecture

### 3.1 Where Atrium lives — recommendation

**Recommendation: extend the existing `mempalace-fork` Starlette app with a Jinja-rendered Atrium UI behind a new `BrowserAuthMiddleware` that requires CF Access service-auth + email-OTP.** Concretely: add new routes `GET /`, `GET /library`, `GET /search`, `GET /agents`, `GET /agents/suggestions`, `GET /agents/reviews`, `GET /settings`, plus `POST /agents/suggestions/<id>/approve|reject|edit` endpoints. All routes served from the same `claude-brain.tstly.dev` host and uvicorn worker as `/mcp`. Atrium reads the **shared agent activity ledger** (per `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`) over HTTPS to Atlas's `/api/agent-ledger/*` endpoints using a service token issued by Atlas.

#### Alternatives compared

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **A. Inside `mempalace-fork` Starlette** (recommended) | One process, one container, one tunnel ingress, one auth surface. Direct read of the same ChromaDB collection and SQLite KG with no marshalling. Zero new infra. | Adds template rendering to a service whose Phase-2 architecture was framed as "API only." Slightly larger Docker image. | ✅ Pick this. |
| B. Separate Coolify service ("`claude-brain-ui`") | Clean separation of MCP and UI. Could iterate the UI on its own deploy cycle. | Two services to keep in sync. Two Cloudflare tunnel rules. Either has to call `/mcp` over the network (slower) or share a volume mount of `palace_path` (footgun for the single-writer invariant). | ❌ Deferred. Reconsider in v0.2.0+ if UI build cycles diverge from MCP build cycles. |
| C. Embedded inside Atlas admin | Re-uses Atlas auth and chrome. Single pane of glass. | Atlas runs Flask; MemPalace runs Starlette; cross-stack data plumbing is the worst kind. Atlas is also single-org/single-DB whereas MemPalace is single-user. | ❌ Wrong place. The Atlas project-track tool is the right fit for *Atlas product-dev* tracking — see §10 Adjacent Systems. |
| D. Separate Electron/desktop app | Native feel; offline read of a local palace mirror. | Heavy. Distribution problem. Mac+Windows+iOS+Android matrix. Defeats the "host the brain on the tunnel" decision in Phase 2. | ❌ Out. |

The recommended Option A also matches the **Atlas Development Delivery Standard V1.1 Cat 9 — Frontend Delivery** rule: server-rendered HTML with progressive-enhancement JS, no bundler, no Tailwind compiler.

### 3.2 Tech stack

| Layer | Choice | Reasoning |
|---|---|---|
| Server | Starlette (already present) | Same app as `/mcp`. No new framework. |
| Templates | Jinja2 | Atlas convention. Matches Cat 9. Trivial to add — Starlette has first-class Jinja2 support. |
| Static assets | Plain CSS file + a single `app.js` (vanilla) | No bundler. ~3 KB CSS using Atlas dark-mode tokens (UI/UX v1.4 §Design Tokens). |
| Interactivity | **HTMX 2.x** (recommended) | Single CDN-pinned `<script src=...>` in the base template. Lets every "approve / reject / refresh feed" interaction be a server-rendered HTML fragment with no client routing. Matches the V1.1 Frontend Delivery "JS-injection shim" pattern from API Doc Review §3 Stub-Routes. Pinned-CDN means we honor Cat 9's "broken CDN pin" rule by versioning the URL. |
| Alpine.js | not needed for v0.1.0 | HTMX covers the interactivity budget. Add Alpine in v0.2.0 only if a richer client-side need lands. |
| Knowledge-graph viz | **deferred to v0.2.0+** — recommendation is **Cytoscape.js** | Reasoning: D3 is the most powerful but most code. vis.js is dated and the maintainer story is unclear. **Cytoscape.js** is purpose-built for typed-edge graphs, has a clean stylesheet API that maps onto the UI/UX color tokens, supports `cose-bilkent`/`fcose` layout out of the box, and ships a single CDN-served JS file (~600 KB) that fits the no-bundler rule. Deferred from v0.1.0 because the rendering surface is the smallest 80%-coverage piece, not because Cytoscape is wrong — when v0.2.0 lights the graph screen, this is the pick. |
| Search UX | HTMX live-search hitting `/search?q=...` | Wraps `mempalace_search` Tool #14. |

### 3.3 Auth — CF Access is a hard pre-ship gate

| Concern | v0.1.1 stance (binding) |
|---|---|
| **CF Access policy on `claude-brain.tstly.dev`** | **HARD PRE-SHIP GATE.** Atrium MUST NOT ship until CF Access (service-auth + email-OTP for `matt@interactep.com` / `luke@interactep.com`) is verifiably in front of `claude-brain.tstly.dev`. This matches the Atlas Security Admin Governance v0.1.0 §2 trust-zone rule (*"Cloudflare edge \| Trusted-with-policy \| Applies Service Auth + Email OTP policies"*). Discovery §E flagged the gate as not-yet-documented-as-live; v0.1.1 of this PRD makes it a binding pre-ship requirement, not a post-ship hardening task. See §3.3.1 for the operational checklist. |
| `/mcp` POST | unchanged. Bearer or OAuth JWT, single worker. **Once CF Access lands, /mcp continues to work via the service-auth header bypass policy** (CF Access service-auth tokens skip the email-OTP challenge so MCP clients keep functioning unchanged). |
| New Atrium routes (`/`, `/library`, `/search`, `/agents`, `/agents/...`, `/settings`) | Behind CF Access (above). The Starlette `BearerAuthMiddleware` already exempts `/health`, `/ready`, `/authorize`, `/oauth/token`, `/.well-known/...`. Add Atrium routes as a third path-class: **CF Access enforces who; bearer/OAuth doesn't apply because the user is a human, not an MCP client.** Implementation: a new middleware that allows Atrium routes through if the `Cf-Access-Authenticated-User-Email` header is `matt@interactep.com` or `luke@interactep.com`, denies otherwise. |
| Atlas ledger API client | **(updated v0.1.2 — per-session per-operator tokens.)** When matt@ or luke@ completes the CF Access OTP challenge, Atrium reads `Cf-Access-Authenticated-User-Email` and exchanges the CF Access JWT for a **short-lived Atlas session token scoped to that operator** by calling `POST /api/auth/exchange` on Atlas. Every subsequent `/api/agent-ledger/*` call from that operator's session carries that per-operator token; Atlas reads the operator from the token directly (no header-forwarding trust). Token lifetime matches the CF Access session (24h). Atrium's only long-lived secret is the **bootstrap service token** used solely to call `/api/auth/exchange` — it cannot read or write the ledger directly. The bootstrap token is stored at `C:\Users\phatt\Desktop\Claude Workspace\Vikunja Deployment\SECRETS_DO_NOT_COMMIT.md` per Atlas Security Admin Governance v0.1.0's secrets-convention durable-backup pattern, with a 90-day rotation cadence. Per-session tokens are not persisted — they live only in Atrium's per-process session state. |
| CSRF on POST `/agents/suggestions/...` | Per-session CSRF token rendered into the HTMX form. Standard Jinja pattern. |
| Logout | Hand-off to the CF Access logout URL; no session cookie of our own. |

### 3.3.1 Pre-ship CF Access checklist (run by Matt at his laptop, BEFORE Atrium build kicks off)

This is operational work — it requires the Coolify dashboard and the Cloudflare Zero Trust dashboard, both of which Matt drives directly. It is **not** part of the Atrium build itself; it is a prerequisite. The full operational note (with screenshot placeholders) lives at `Claude Workspace\mempalace-fork\docs\architecture\03-cf-access-setup-v0.1.0.md` — this section is the summary.

| # | Step | Verification |
|---|---|---|
| 1 | **Verify the existing CF Tunnel for `claude-brain.tstly.dev` is healthy.** It was last confirmed in deployment session log v1.10–v1.15. | `curl -fsS https://claude-brain.tstly.dev/health` returns 200 from outside the LAN. |
| 2 | **In the Cloudflare Zero Trust dashboard, create a new CF Access *application* for `claude-brain.tstly.dev`** (Self-hosted application, full hostname match). | Application appears in Access → Applications. |
| 3 | **Attach Policy 1 — Service Auth.** Create a service-auth token named `mempalace-atrium-svc`. Bind the policy to "Include: Service Auth – Token = mempalace-atrium-svc". | Policy listed; token client-id/secret captured. |
| 4 | **Attach Policy 2 — Allow (email OTP).** "Include: Emails – `matt@interactep.com`, `luke@interactep.com`. Authentication: One-time PIN." | Policy listed; precedence: Service Auth before Allow. |
| 5 | **Store the service-auth token client-id/secret durably** at `C:\Users\phatt\Desktop\Claude Workspace\Vikunja Deployment\SECRETS_DO_NOT_COMMIT.md` per Atlas Security Admin Governance v0.1.0 secrets convention. | File contains a clearly labeled `mempalace-atrium-svc` block with rotation date. |
| 6 | **Test the gate — anonymous request.** From a clean browser: `https://claude-brain.tstly.dev/`. | Returns 302 to the Cloudflare Access OTP challenge page. |
| 7 | **Test the gate — email OTP success.** Complete OTP for `matt@interactep.com`. | Reaches the Starlette app (currently 404 on `/`; that's expected pre-Atrium-build — the point is to confirm Access let the request through). |
| 8 | **Test the gate — service-auth bypass.** With `CF-Access-Client-Id` and `CF-Access-Client-Secret` headers set, hit `POST /mcp` with the existing OAuth JWT. | 200, JSON-RPC envelope returned, no OTP challenge. |
| 9 | **Document the working state in the Vikunja deployment log** (next session entry, v1.16 or whatever is current). | Log line with timestamps and screenshots of all four green states. |

**Only after all nine steps pass does Atrium build begin.** Failure on any step blocks the build. Re-test step 8 daily during build to catch CF policy drift.

### 3.4 Data layer

**Recommendation: direct read access to ChromaDB + SQLite for the read paths; mutations always route through the existing MCP tools.**

| Path | Access | Reason |
|---|---|---|
| `tool_status`, `list_wings`, `list_rooms`, `taxonomy`, `graph_stats`, `find_tunnels`, `traverse` (UI read paths) | Direct `chromadb.PersistentClient(...).get(include=['metadatas'])` paginated reads | A full-page Jinja render needs to fan out to ~5 of these and over `/mcp` would round-trip JSON-RPC 5×, each behind the single asyncio Lock that serializes /mcp. Local reads are sub-100ms; serialized RPC is multi-second. |
| `kg_query`, `kg_timeline`, `kg_stats` | Direct SQLite read of `<palace_path>/knowledge_graph.sqlite3` | Same reason. The KG class is already thread-safe (`check_same_thread=False`). |
| `search` | Wrap `searcher.search_memories` directly | Same module; no need to RPC ourselves. Keeps the prompt-injection sanitizer in the path. |
| **Memory-palace writes** (canonical drawer/triple writes triggered by approve/edit) | **Through `mempalace_add_drawer` / `mempalace_delete_drawer` / `mempalace_kg_*` via the existing MCP path** | Preserves the WAL audit trail. Preserves the duplicate-check, sanitization, idempotency. Single source of truth for the rate-limiter. |
| **Ledger writes** (suggestion state transitions, review verdicts, run lifecycle) | **Through Atlas's `/api/agent-ledger/*` REST surface** with the `mempalace-atrium-svc` Atlas service token | Single source of truth for agent activity across Atrium AND the Atlas project-track tool. State (pending → approved/rejected/edited) lives in `agent_suggestions`; verdicts live in `agent_reviews`. See `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` §5 for the API contract. |

This is the same pattern the API Documentation Review §3 sketches: "stub routes for the UI; canonical mutations go through the documented API." Memory-palace canonical mutations go through MCP; agent-activity canonical mutations go through the Atlas ledger API. [API Doc Review §3 Stub-Routes Pattern, **[v0.1.2 backfill]** when the framework lands].

---

## 4. Adjacent Systems & Boundary

### 4.1 The upcoming Atlas project-track tool

A separate tracker over agentic work, scoped to **Atlas product development** (the canonical skill chain — atlas-delivery-standard → build-tester → code-review-optimizer → atlas-pre-push-review → cowork-git-push → coolify-feature-branch — per AI Agentic Review §2). Different surface, different host, different audience. **Atrium and the Atlas project-track tool share the same agent activity ledger** (specified once in `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`, hosted in Atlas Postgres):

| Concept | Atrium | Atlas project-track tool |
|---|---|---|
| Agent activity ledger | reads `agent_runs` rows (surface = atrium / both / global) over Atlas REST API | reads `agent_runs` rows (surface = project-track / both / global) directly from Atlas Postgres |
| Suggestion queue | drawer / triple drafts: `wing_inbox` carries the payload, `agent_suggestions` carries state | task drafts in a Vikunja-like board: Vikunja carries the payload, `agent_suggestions` carries state |
| Reviews | approve/reject/edit on a draft → `agent_reviews` row | merge / decline on a PR/task → `agent_reviews` row |
| Persona registry | shared `agent_persona_registry` rows (e.g. Cartographer/Magellan with scope=atrium or both) | same table, different scope filter |
| Pause-Before-Irreversible-Action | ✅ all writes are explicit | ✅ pre-push review skill blocks |
| Three-Agent Integrity Score | reviews from Atrium feed §7.4 score input | reviews from project-track feed §7.4 score input |

The Atlas project-track tool's design doc (when it exists) should reference this section + `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` so the boundary is documented from both sides. [AI Agentic Review §4 Update #1 — *Cowork-Runtime Governance Agents* class. **[v0.1.2 backfill]** when AI Agentic v2.2 lands.]

### 4.2 The MemPalace MCP tool surface

Atrium is layered **on top of** the 19 tools, not next to them. Anything the MCP tools can't already do, Atrium doesn't add — it visualizes. New screens that imply a missing read (e.g. "list of all agents that have ever written") may motivate a 20th tool, but that's a v0.2.0+ conversation.

### 4.3 The Atlas REST surface (new dependency)

v0.1.1 introduces a runtime dependency Atrium did not have in v0.1.0: Atrium calls Atlas's `/api/agent-ledger/*` endpoints from `claude-brain.tstly.dev`. Failure modes and mitigations:

| Failure | Atrium behavior |
|---|---|
| Atlas API unreachable | Read paths degrade to "ledger unavailable" banner; memory-palace browse paths (Library, Search, /drawer/*) keep working unaffected. |
| Atlas API returns 401/403 | Surface the error in the Atrium settings page; block all suggestion/review POSTs. |
| Atlas API slow (>2s) | Atrium read paths use a 5s timeout with cached last-known-good values for the right-rail Activity Feed. |
| Service-token rotation | Documented in §3.3 row 5; Atrium re-reads token from disk on SIGHUP (no full restart). |

---

## 5. Tech Conventions Inherited from Atlas Governance

| Concern | Source | Convention |
|---|---|---|
| Dark mode by default; light/dark/adaptive toggle | UI/UX **v1.4** §Color Mode Standards | Default = adaptive; sidebar footer toggles state. **[v0.1.1 backfill]** for v1.5. |
| Design tokens; no hardcoded colors | UI/UX v1.4 §Design Tokens | Use `--bg-primary`, `--bg-card`, `--text-primary`, `--accent-blue`, etc. Mockup §3 lists exact token values. |
| Sidebar 220–260 px expanded / 60 px collapsed; icon+label rule | UI/UX v1.4 §Sidebar Navigation | Mockups §1.1 follows. |
| 8-zone record-page layout | UI/UX v1.4 §Standard Page Layout | Drawer detail page (Mockup §2.2) follows. |
| Quick Actions in record header (max 4 + overflow) | UI/UX v1.4 §Quick Actions | Drawer header has Edit · Move · Delete · ⋮ (Pin / Copy ID / Open WAL row). |
| Frontend Delivery: server-rendered, no bundler | Atlas Development Delivery Standard V1.1 Cat 9 | Jinja + HTMX; CDN pin versioned. |
| Pause Before Irreversible Action | AI Agentic Review §4 Update #3 (proposed §2.10 of v2.2). **[v0.1.1 backfill]** | Approve/Reject is an explicit click; edit-then-approve is two clicks. Never auto-approve. |
| State outside the sandbox | AI Agentic Review §4 Update #4 | The UI never persists state in browser localStorage beyond cosmetic prefs (sidebar collapsed, last-opened-wing). Real state lives in ChromaDB / SQLite / WAL. |
| API URL conventions | API Doc Review §2 | UI's POST endpoints follow `/agents/suggestions/<id>/<verb>`. |
| Migration naming for shared ledger tables | Database Governance v0.1.0 §4 | Migrations land in **Atlas's** alembic chain (not MemPalace's), naming per the Atlas convention in force at the time. The shared ledger schema doc specifies tables/columns/FKs/indexes only — no SQL, no migration files. Atrium adds **no** new SQLite tables to the MemPalace fork in v0.1.0. |


---

## 6. Key Screens (v0.1.0)

Each screen below specifies (a) what it shows, (b) which MCP tool / direct read each datum comes from, (c) what the user can do.

### 6.1 Palace Overview / Home (`GET /`)

**Purpose.** A glance at the brain — does it look healthy, what's been added recently, how big is each wing.

**Data.**
- Top KPI tiles: total drawers, total wings, total triples, total agents-with-diaries. → `tool_status` (Tool #1) + `tool_kg_stats` (Tool #10).
- Per-wing card grid (one card per wing, sorted by drawer count). Each card shows wing name, drawer count, top 3 rooms, last-touched date. → `tool_get_taxonomy` (Tool #4) + a one-shot pagination over `metadatas` to compute `last_touched_per_wing` (the Discovery §A drawers carry `filed_at`; aggregating is local).
- Right-rail "Recent activity" feed — last 25 entries from the WAL JSONL (Discovery §A.8), newest first. Each row: timestamp, operation badge, wing/room or entity, a one-line preview, an Open link.

**Actions.** None (read-only). Click a wing card to drill into Library (§6.2) for that wing. Click a WAL row to drill into the Drawer Detail page for that drawer (or KG fact).

**Why it matters.** Replaces "I have to ask Claude `mempalace_status`" with "open `claude-brain.tstly.dev/`."

### 6.2 Drawer Browser (`GET /library`, `GET /library/<wing>`, `GET /library/<wing>/<room>`, `GET /drawer/<id>`)

**Purpose.** Browse what's in the palace structurally — Wing → Room → Drawer.

**Data.**
- Wing index: `tool_list_wings` (Tool #2).
- Room list inside a wing: `tool_list_rooms(wing)` (Tool #3) sorted by drawer count.
- Drawer list inside a room: paginated direct read of ChromaDB with `where={"wing": ..., "room": ...}` (Discovery §A.1). Columns: filed-at, source-file, added-by, content-preview (first ~200 chars).
- Drawer detail: full content + metadata + the WAL line that filed it (matched on `params.drawer_id`).

**Actions.**
- Inline copy-link-to-drawer (URL of the form `/drawer/drawer_wing_room_<hash>`).
- "Open in Search" (pre-fills `/search?q=` with the first sentence — useful for "what else like this").
- v0.1.0 explicitly does NOT have inline edit / delete on drawers from the Library — those route through Suggestions (§6.6).

### 6.3 Search (`GET /search?q=...&wing=...&room=...&limit=...`)

**Purpose.** Single-box semantic search across the whole palace.

**Data.**
- Wraps `tool_search` (Tool #14). Surfaces the `_sanitization` block when the sanitizer trimmed or rewrote the query, so Matt can see what actually got queried.
- Optional facet sidebar: filter by wing, room, hall, added-by, date-range.
- Result row: drawer-id, wing/room badges, similarity score, content snippet with the matching span highlighted (server-side, regex over the matched terms — no JS dep).

**Actions.** Click → Drawer Detail (§6.2). Save-this-search button → deferred to v0.2.0+.

### 6.4 Knowledge Graph (`GET /kg`) — **deferred to v0.2.0+**

**Purpose.** Node-link visualization of `entities` + `triples`.

**Status.** v0.1.0 ships a *placeholder page* with a textual table view of `tool_kg_stats` and `tool_kg_timeline` (no entity argument = full timeline) so KG data is at least visible. The interactive Cytoscape layout is v0.2.0.

**Data (v0.1.0 placeholder).** `tool_kg_stats` (Tool #10), `tool_kg_timeline` (Tool #9), and a per-entity drilldown that calls `tool_kg_query` (Tool #6). Direct SQLite read.

### 6.5 Agent Activity Feed (`GET /agents`)

**Purpose.** Chronological list of agent activity, grouped by run.

**Data.**
- Primary feed: `GET /api/agent-ledger/runs?surface=atrium&order=-started_at&limit=50` returns recent `agent_runs` rows (id, agent_name, agent_version, started_at, ended_at, status, surface, parent_run_id, input_summary, output_summary). Each run is collapsible — clicking expands to show the run's `agent_suggestions` rows (created_at, type, state) and `agent_reviews` rows (verdict, rationale).
- Secondary feed (under the run summary, when expanded): the WAL JSONL lines that fall inside `[run.started_at, run.ended_at]` — gives byte-level visibility into what the run actually wrote to ChromaDB. Joined client-side by timestamp range.
- Diary feed (right rail or toggle): all `wing_<agent>/diary` entries, newest first, across all agents. Direct ChromaDB read with `where={"hall": "hall_diary"}`.

**Actions.** None (v0.1.0). Filter by agent_name, by status (running/idle/error/blocked), by surface, by date range. v0.2.0 adds "subscribe to this agent's diary" and live-WebSocket updates.

### 6.6 Agent Suggestions Queue (`GET /agents/suggestions`)

**Purpose.** The interactive surface. Pending writes, awaiting Matt/Luke's approve / decline / edit.

**Data model for v0.1.0 — formal `agent_suggestions` schema** (per `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` §3, lives in **Atlas Postgres**):

The pattern split:
- **Payload (the proposed drawer content)** — written into ChromaDB at `wing_inbox/<agent>-<topic>` via `mempalace_add_drawer(...)`. Same as v0.1.0. ChromaDB stays the single source of truth for verbatim content.
- **State, target, lineage, verdict (the workflow)** — recorded in Atlas Postgres tables specified in the shared ledger schema:
  - `agent_runs` row (every suggestion belongs to a run; the run is opened when the agent starts working and closed when it returns).
  - `agent_suggestions` row with `target_kind=drawer`, `target_id=<the inbox drawer_id>`, `suggestion_type=create`, `payload` JSONB carrying `target_wing`, `target_room`, `proposed_drawer_id`, content hash, agent self-confidence, etc., `state=pending`, `created_at`.
- The Suggestions Queue UI is a join: `SELECT s.*, r.agent_name, r.agent_version FROM agent_suggestions s JOIN agent_runs r ON s.agent_run_id = r.id WHERE s.state = 'pending' AND s.surface IN ('atrium', 'both', 'global') ORDER BY s.created_at ASC`. Atrium retrieves this via `GET /api/agent-ledger/suggestions?state=pending&surface=atrium` and renders.
- Each suggestion row shows: agent_name (from join), agent persona (from `agent_persona_registry` join — e.g. "Cartographer / Magellan"), target wing/room (from `payload`), content preview (fetched from ChromaDB by `target_id`), age, governance_tier badge (auto / supervised / approval_gated).

**Actions on a suggestion (POST `/agents/suggestions/<suggestion_id>/<verb>`):**

| Verb | What happens server-side |
|---|---|
| `approve` | (1) Atrium calls `mempalace_add_drawer(wing=payload.target_wing, room=payload.target_room, content=<retrieved>, added_by="<reviewer>+<agent>")` to promote the canonical drawer (WAL-logged). (2) Atrium calls `mempalace_delete_drawer(<inbox_drawer_id>)` to remove the staging copy (WAL-logged). (3) Atrium calls `POST /api/agent-ledger/suggestions/<id>/resolve` with `{state: 'approved', resolved_by_user_id: <Matt|Luke>, note?}` to flip ledger state. (4) Atrium creates an `agent_reviews` row via `POST /api/agent-ledger/reviews` with `verdict=approve`, `action_taken=promoted_to_<target_wing>/<target_room>`. |
| `reject` | (1) Atrium calls `mempalace_delete_drawer(<inbox_drawer_id>)` to remove the staging copy. (2) `POST /api/agent-ledger/suggestions/<id>/resolve` with `{state: 'rejected', resolved_by_user_id, note}` (note required for reject — the reviewer must say why). (3) `POST /api/agent-ledger/reviews` with `verdict=decline`, `action_taken=deleted_inbox_drawer`. |
| `edit` | Render the content in a textarea (HTMX inline form). On save: (1) `mempalace_add_drawer(target_wing, target_room, edited_content)` for the canonical write. (2) `mempalace_delete_drawer(inbox_id)`. (3) `POST /api/agent-ledger/suggestions/<id>/resolve` with `{state: 'edited', resolved_by_user_id, note: <diff_summary>}`. (4) `POST /api/agent-ledger/reviews` with `verdict=request_changes` (the edit IS the request) + `action_taken=edited_and_promoted`. |

This is **the** Pause-Before-Irreversible-Action surface (AI Agentic Review §4 Update #3). Every action is one explicit click. The edit verdict produces a complete audit chain: the original payload (in ChromaDB before deletion → recoverable from WAL JSONL), the edited final drawer (in ChromaDB), the diff (in `agent_reviews.rationale`), and the lineage (`agent_runs` → `agent_suggestions` → `agent_reviews`). No batch-approve in v0.1.0.

**Why the split (payload in ChromaDB, state in Atlas Postgres):** the proposed content is verbatim memory data and belongs in the memory store; the workflow / who-decided-what is operational governance and belongs next to Atlas's other operational tables. A single ChromaDB record cannot cleanly express state transitions over time, and a single Postgres row cannot cleanly carry the embedding-indexed semantic content. The split keeps each store doing what it does well, and the `agent_suggestions.target_id` FK is the join key.

### 6.7 Agent Reviews (`GET /agents/reviews`)

**Purpose.** History of completed suggestions: what was proposed, what was decided, who decided.

**Data — formal `agent_reviews` schema** (per `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` §3, lives in Atlas Postgres):

A single API call: `GET /api/agent-ledger/reviews?surface=atrium&order=-created_at&limit=100`. Each row carries `id`, `agent_run_id` (FK), `reviewed_target_kind`, `reviewed_target_id`, `verdict` (`approve` / `decline` / `request_changes`), `confidence_score`, `rationale`, `action_taken`, `created_at`. Atrium joins on `agent_runs` for `agent_name` + `agent_version`, and on `agent_persona_registry` for the persona label.

The page renders: date, agent (+ persona), reviewer (resolved from `agent_suggestions.resolved_by_user_id`), verdict, target (link to the now-canonical drawer if approved, or "deleted" if rejected), one-line rationale.

**Actions.** None (read-only). Filter by reviewer, by agent, by verdict, by date range. Click a row → diff view between the original suggestion content and the final approved drawer (server-side rendered diff using `difflib.unified_diff` against the WAL-recoverable original payload).

**Integration with §7.4 Three-Agent Integrity Score.** Each `agent_reviews` row contributes to the agent's review track-record. Approved-without-edit is a strong positive signal; reject and edited verdicts are negative/corrective. The Integrity Score consumes `agent_reviews` directly via the same Atlas REST surface — see `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` §6.

### 6.8 Settings (`GET /settings`)

**Purpose.** Operational levers.

**Sections.**
- **Identity** — show the contents of `~/.mempalace/identity.txt` (read-only in v0.1.0; editing this is locked per Phase 2 architecture A8).
- **Wings** — list of wings + drawer counts. Read-only in v0.1.0; rename / merge / delete is v0.2.0+.
- **Connectors** — show the four connector targets (claude.ai web, mobile, Cowork, Claude Desktop) with their last-seen timestamps from the WAL `added_by` field. Read-only.
- **Audit log** — link out to `/agents` (the WAL feed is the audit log).
- **Bearer token rotation** — instructions only (rotation is still a CLI / Coolify operation per Phase 10 v1.14).
- **About** — version (`mempalace.version.__version__`, currently `3.0.14`), git SHA if available, deployed-at, palace path.

---

## 7. Interaction Patterns

| Pattern | Spec |
|---|---|
| **Keyboard shortcuts** | `/` focus search; `g h` go home; `g l` library; `g a` agents; `g s` settings; `?` help overlay; `j` / `k` move down/up in feeds; `enter` open. Implemented as a single ~30-line vanilla-JS keymap (no library). |
| **Deep linking** | Every drawer is `/drawer/<id>`. Every WAL row is `/agents#wal-<line-hash>`. Every search is `/search?q=...&wing=...`. URLs survive sharing. |
| **Copy-link-to-drawer** | Drawer page has a copy-icon button next to the ID; copies the canonical `claude-brain.tstly.dev/drawer/<id>` URL. |
| **Live updates** | The Agent Activity Feed (§6.5) and the Suggestions Queue (§6.6) auto-refresh every 5 s via HTMX `hx-trigger="every 5s"` on a small wrapper div. No WebSocket in v0.1.0. |
| **Empty / loading / error states** | UI/UX v1.4 §"Close the Loop" — every action shows a result. Empty wings show "No drawers in this room yet — file with `mempalace_add_drawer`." |
| **Mobile** | Tablet-friendly per UI/UX v1.4 §Mobile Awareness. Sidebar goes off-canvas under 768 px. Phone is best-effort, not v0.1.0 priority. |

---

## 8. Naming — locked

**Atrium, locked v0.1.1, no further discussion needed in v1.**

(v0.1.0 of this PRD proposed six candidates and recommended Atrium; Matt picked Atrium on 2026-04-28.)

---

## 9. Governance — citations & gaps

| Source | Used for | Status |
|---|---|---|
| Atlas Development Delivery Standard **V1.1** | Cat 9 Frontend Delivery (server-rendered, no bundler), Cat 4 Permissions (auth choice), Cat 1 Schema (the shared ledger schema lives in Atlas Postgres alembic chain — *Atrium does not own the schema*) | ✅ live, cited inline |
| UI/UX **v1.4** | Design tokens, sidebar dimensions, page layout, dark-mode tokens, button placement, inline-editable fields | ✅ cited; **[v0.1.2 backfill]** — re-cite to v1.5 when it lands |
| AI Agentic — **Review v0.1.1** (no v2.2 yet) | Pause Before Irreversible Action; Cowork-Runtime Governance Agents class; canonical skill chain; sandbox-state rule; **§7.4 Three-Agent Integrity Score** integration with `agent_reviews` | ⚠️ cited as Review v0.1.1; **[v0.1.2 backfill]** — re-cite to v2.2 when it lands |
| Database Governance **v0.1.0** | Migration naming for the shared ledger (lives in Atlas alembic chain); ENUM-over-bucket-id-FK rule for `agent_runs.status` and `agent_suggestions.state`; multi-instance inventory (Atlas Postgres now hosts agent activity) | ✅ cited |
| Security Admin Governance **v0.1.0** | **CF Access service-auth + email-OTP at the CF-edge zone (now binding pre-ship gate per §3.3)**; cross-zone hop rule; secrets-convention durable-backup pattern (`SECRETS_DO_NOT_COMMIT.md`) for the service-auth token | ✅ cited inline in §3.3 Auth + §3.3.1 Pre-ship checklist |
| API Documentation — **Review v0.1.0** (no framework yet) | Stub-routes pattern; URL conventions; JSON contract conventions for `/api/agent-ledger/*` | ⚠️ cited as Review v0.1.0; **[v0.1.2 backfill]** — re-cite to API Doc Framework v0.1.0 when it's promoted from review |
| **Atlas Agent Activity Ledger Schema v0.1.0** (new in v0.1.1) | Tables, RLS, REST API contract that Atrium consumes for `agent_runs` / `agent_suggestions` / `agent_reviews` / `agent_persona_registry` | ✅ new dependency; co-designed with Atlas project-track tool |

Three rows are still placeholder citations that need a v0.1.2 of this PRD when the missing governance frameworks land. Not a blocker for the build; a blocker for "all citations canonical."

---

## 10. Adjacent Systems — Atlas project-track tool

A separate tracker over agentic work, scoped to **Atlas product development** and living in the Atlas admin surface (Flask, not Starlette; Atlas Postgres for both its own data and now the shared ledger). The two surfaces overlap on the **agent-activity-ledger** pattern and now **share** that ledger directly.

**v0.1.1 update — schema is shared, deferral dropped.**

1. v0.1.0 of Atrium uses the formal `agent_runs` / `agent_suggestions` / `agent_reviews` / `agent_persona_registry` tables (Atlas Postgres) per `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md`. The WAL JSONL is retained as a byte-level secondary feed but no longer the primary activity ledger.
2. The Atlas project-track tool reads/writes the same tables, scoping by `surface IN ('project-track', 'both', 'global')`.
3. Persona registry is shared: an agent registered as `agent_name='claude-export'` with `scope='both'` shows up in both surfaces with the same persona metadata.
4. Boundary: Atrium's `surface='atrium'` rows are not visible in project-track unless `scope='both'` or `'global'`; same in reverse. Both surfaces always see `'global'` rows. Atlas RLS enforces this filtering at the database layer regardless of which API path enters.

When the Atlas project-track tool's PRD is written, link back to this PRD §4.1 + §10 so the boundary is documented from both sides, and reference `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` as the canonical schema source.

---

## 11. Open Questions for Matt's judgment

> **v0.1.1 status.** Q1 (naming), Q2 (auth), Q3 (inbox model) resolved. Renumbered.

1. ~~**Tool name.**~~ **RESOLVED v0.1.1: Atrium.** Locked.
2. ~~**Auth before merge.**~~ **RESOLVED v0.1.1:** CF Access is a hard pre-ship gate (§3.3 + §3.3.1).
3. ~~**Suggestions inbox model.**~~ **RESOLVED v0.1.1:** content carrier is `wing_inbox` (single shared wing, ChromaDB); state lives in `agent_suggestions` (Atlas Postgres). The schema's `agent_run_id` + `payload.target_wing/target_room` carries the per-agent attribution; no separate `wing_inbox_<agent>` needed.
4. **Knowledge-graph viz priority.** Cytoscape viz is deferred from v0.1.0. Confirm — or pull it forward at the cost of stretching the v0.1.0 build.
5. **Delete/edit-from-Library.** v0.1.0 routes all mutations through Suggestions. Confirm — or expose direct delete for Matt-himself as a tier-1 admin action.
6. **Versioning of governance citations.** The PRD has three placeholder citations (UI/UX v1.5, AI Agentic v2.2, API Doc v0.1.0). Matt's call: ship the build before backfill, or wait for the docs.
7. **Voice mode hand-off.** Voice-mode is parked (ISSUE-5, v1.13). Out of scope for v0.1.0 Atrium; flagged here so it isn't forgotten.
8. **Live update cadence.** The 5-second HTMX refresh (§7) — Matt's preference is faster (1s, snappier) or slower (15s, lighter)?
9. ~~**(new in v0.1.1) Atlas API readiness.**~~ **RESOLVED v0.1.2:** critical-path-serial with parallel tracks. See §12.
10. ~~**(new in v0.1.1) Persona registration ceremony.**~~ **RESOLVED v0.1.2:** YAML + bootstrap script + live editor in Settings + block-by-default. See §13.

---

## 12. Build Order (new in v0.1.2)

The dependency: Atrium hard-depends on Atlas's `/api/agent-ledger/*` and `/api/auth/exchange` being live. The fast path is **critical-path-serial with parallel tracks** — the gating sequence is short, and everything that can run alongside it does.

| Track | Step | Depends on | Output |
|---|---|---|---|
| **A — Atlas (critical path)** | A1. Schema migration: provision `agent_ledger` schema and four tables in Atlas Postgres alembic chain | nothing | tables live |
| **A — Atlas (critical path)** | A2. Persona registry bootstrap (YAML + script — see §13) | A1 | seed roster live |
| **A — Atlas (critical path)** | A3. Implement REST endpoints: `/api/auth/exchange`, `/api/agent-ledger/runs`, `/suggestions`, `/reviews`, `/personas` | A1, A2 | endpoints live, smoke-tested with curl from `claude-brain.tstly.dev` |
| **A — Atlas (critical path)** | A4. RLS rules per schema §4; audit-trigger wiring | A3 | full Atlas auth + audit posture |
| **B — Atrium (parallel with A)** | B1. CF Access pre-ship checklist (per `docs/architecture/03-cf-access-setup-v0.1.0.md`) | nothing | gate live, all 9 steps green |
| **B — Atrium (parallel with A)** | B2. Atrium UI shell — Starlette routes, Jinja base templates, sidebar, dark-mode tokens, static CSS, HTMX CDN pin | nothing | empty Atrium reachable behind CF Access |
| **B — Atrium (parallel with A)** | B3. Static read screens that don't touch the ledger: Library (§6.2), Search (§6.3), KG placeholder (§6.4), Settings non-persona sections (§6.8) | B1, B2 | half of Atrium browseable |
| **C — Integration (gated on A and B)** | C1. Atrium ledger client — bootstrap token storage, `/api/auth/exchange` flow, per-session token lifecycle | A3, B2 | Atrium can authenticate to Atlas ledger |
| **C — Integration** | C2. Suggestions Queue (§6.6), Reviews (§6.7), Activity Feed (§6.5) | C1 | Atrium feature-complete for v0.1.0 |
| **C — Integration** | C3. Persona registry editor in Atrium Settings (§13) | C1 | persona governance editable from UI |
| **C — Integration** | C4. Atlas project-track tool wires to the same ledger | A3, A4 | shared ledger in production use across both surfaces |

The critical path through the table is A1 → A2 → A3 → C1 → C2. Tracks A and B run concurrently. Track B never blocks A. Track C waits on the merge.

Suggested execution: spawn A and B as parallel sub-agents (or parallel humans), each with their own Coolify branch and feature env per `coolify-feature-branch` skill conventions.

---

## 13. Persona Registration (new in v0.1.2)

The `agent_persona_registry` table is **the roster of agents authorized to write to the ledger**. For a work tool (not an MVP), silent auto-create is the wrong posture — surprise agents writing to the palace defeat the accountability the ledger exists to give. The model below is hybrid and version-controlled.

### 13.1 The model

1. **YAML source of truth** — `agent_personas.yaml`, checked into the Atlas repo. One block per authorized agent:

   ```yaml
   - agent_name: claude-export
     persona_archetype: Cartographer
     persona_label: Magellan
     persona_description: Extracts conversations from Claude.ai exports, files into wing_inbox for review.
     scope: atrium
     governance_tier: approval_gated
   ```

   Putting the roster under version control means every persona change is a PR with a reviewer and a git history. That's what a work tool needs.

2. **Bootstrap script — `bootstrap_personas.py`** (lives in the Atlas repo). UPSERTs each YAML block into `agent_persona_registry` on every Atlas deploy. Idempotent — re-runs are safe. New persona on next deploy; updated description / governance_tier on next deploy.

3. **Live registry editor in Atrium Settings (§6.8 + Mockups §2.8) and the Atlas project-track Settings.** A simple form per persona — change `governance_tier` (auto / supervised / approval_gated), edit `persona_description`, retire (set `retired_at`). Saves directly to the table AND nudges the operator to commit the matching YAML change ("Don't forget to commit `agent_personas.yaml` so this survives the next deploy"). Optional v0.2.0+ enhancement: a PR-bot that opens the YAML PR automatically.

4. **Block by default for unregistered agents.** Any `agent_name` that has no row in `agent_persona_registry` cannot write — the API returns 403 with `{error_code: "agent_not_registered", message: "Add a row to agent_persona_registry first."}`. The friction of adding the row IS the security check. For a roster on the order of 5–15 agents over the lifetime of the tool, hand-curated registration is trivial cost.

### 13.2 Initial seed roster (illustrative)

The v0.1.0 ship-time YAML covers at minimum:

| agent_name | archetype | label | scope | tier |
|---|---|---|---|---|
| `claude-export` | Cartographer | Magellan | atrium | approval_gated |
| `claude-mining` | Cartographer | Mercator | atrium | approval_gated |
| `mcp` | Navigator | (laptop) | global | supervised |
| `coverage-checker` | Surveyor | (TBD) | project-track | approval_gated |

(Final list — and final persona names — is Matt's pick at bootstrap time.)

### 13.3 Promotion path

A persona ships at `approval_gated` (every suggestion needs explicit human review). After a sustained track record visible in the ledger — a high approval-without-edit rate over a rolling window, low confidence-divergence between agent self-confidence and reviewer confidence — Matt promotes the persona to `supervised` via the Settings editor. `auto` is reserved for hand-granted high-trust mechanical agents and is set in the YAML, never auto-promoted by score.

### 13.4 Retirement

When an agent is decommissioned, set `retired_at` via the Settings editor (or in the YAML). Existing `agent_runs` rows pointing at the retired persona are preserved (audit trail intact). New writes from a retired agent_name are blocked with the same 403 as unregistered.

---

End of PRD v0.1.2.
