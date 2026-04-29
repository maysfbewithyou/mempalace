# MemPalace Deployment — Session Log v1.10

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.9.

---

## v1.0–v1.9 — Decision phase complete

All nine decisions D1–D9 locked. See per-version logs for individual lock entries:

- v1.0: Phase 0 audit, Discovery Report v0.1, STOP gate.
- v1.1: D1 — Path A, Coolify single source of truth.
- v1.2: D2 — bearer-token auth first; OAuth deferred to Phase 10.
- v1.3: D3 — four wings: `wing_mega`, `wing_iep`, `wing_atlas`, `wing_personal`.
- v1.4: D4 — fresh Claude.ai export requested.
- v1.5: D5 — Slack deferred to Phase 11.
- v1.6: D6 — Phase 9 closeout (commit docs + tag + clean stale branch).
- v1.7: D7 — Hybrid hooks + scheduled weekly agentic review.
- v1.8: D8 — Monthly upstream sync + manual merges + scheduled diff report.
- v1.9: D9 — Draft C (~95 token) identity layer.

---

## v1.10 — Phase 2 Architecture locked + Claude.ai export inspected (2026-04-27)

### Phase 2 Architecture v0.2 — LOCKED

Document path: `MemPalace_Phase_2_Architecture_v0.2.md` (with v0.1 preserved as rollback anchor).

**Eight architecture decisions ratified:**

| ID | Decision | Locked value |
|---|---|---|
| A1 | Tunnel domain | `mempalace.tstly.dev` (Matt confirmed `tstly.dev` is his domain) |
| A2 | Container Python | `python:3.12-slim` (best ChromaDB 0.5.x compat) |
| A3 | HTTP wrapper library | Starlette + uvicorn (subprocess-proxy approach) |
| A4 | Worker count | Single uvicorn worker (palace-consistency requirement) |
| A5 | Bearer token storage | `C:\Users\phatt\.mempalace_client\token` (file mode 0o600 equivalent) |
| A6 | `/health` endpoint | Public, unauthenticated |
| A7 | First-boot bootstrap | YES — auto-run `mempalace init` + write identity.txt if volume empty |
| A8 | Resource limits | 1 GB mem / 1.0 CPU (revisit after 1 week of mining) |

**Approach summary:** keep upstream `mempalace.mcp_server` untouched; add new file `mempalace/http_server.py` as a Starlette/uvicorn HTTP wrapper that **subprocess-proxies** to upstream's stdio MCP. Bearer-auth middleware. Single worker. New Dockerfile + Coolify compose service + Cloudflare tunnel ingress rule for `mempalace.tstly.dev`.

**Phase 2 sub-phases (locked execution order, total est. 2.5–4 hrs of focused work):**

- 2a — Write wrapper code + tests in fork (1–2 hrs).
- 2b — Dockerfile + local container smoke-test (30 min).
- 2c — Coolify service deploy (30 min).
- 2d — Cloudflare tunnel ingress for `mempalace.tstly.dev` (15 min).
- 2e — End-to-end smoke tests (5 checks: tunnel/health/auth-reject/auth-accept/MCP round-trip/tools-list/Cowork query).

### Claude.ai export inspected

Matt uploaded the export ZIP. Inspection (read-only, no mining):

- 69 conversations, 3,238 messages, spanning 2026-01-24 to 2026-04-27.
- 4 files inside ZIP: `users.json`, `projects.json` (7 Claude.ai projects), `memories.json`, `conversations.json` (20.9 MB).
- Content blocks include `text`, `tool_use`, `tool_result`, `thinking` — full tool-call traces.
- Naive title-keyword routing preview: 21 → wing_iep, 18 → wing_atlas, 9 → wing_mega, 21 unrouted. Naive matcher had misroutes; Phase 6 will use an LLM-driven classifier with human spot-check before mining.
- **Skip list confirmed:** "Evander's conversation with Claude" (144 msgs) — someone else's content, will not be mined.
- **Routing confirmations (locked):** "IEP subcontractor agreement for LA Fairgrounds" → `wing_iep`; "Mempalace integration review" → `wing_atlas`.
- File location: Cowork session uploads (path archived but not deleted per Matt's filesystem policy). Phase 6 will locate by name pattern at execution time.

### Issues carried forward

- ISSUE-1 (BLOCKER): Pytest 85/85 not re-verified — Phase 1 gate. Awaiting Matt's local run.
- ISSUE-2 (Phase 7 dep): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-4 (Phase 2 work, design locked): HTTP MCP wrapper — implementation begins after Phase 1 clears.
- ISSUE-5 (parked, Phase 10): voice-mode tool support — Matt testing externally.
- ISSUE-6 (parked, Phase 6): Claude.ai export inspected, mining queued post-Phase 5.
- ISSUE-7 (parked, Phase 11): Slack mining design.
- ISSUE-8 (Phase 8): Verify Stop hook merge behavior.

### Next gate

Phase 1 (pytest 85/85 from Matt's terminal) is the sole blocker between here and Phase 2a code-writing.

### Versioning policy

Every artifact carries a version stamp. Decision and design locks bump session-log minor version. Each prior log version preserved as a rollback anchor.
