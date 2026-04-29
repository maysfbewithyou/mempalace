# MemPalace Deployment — Session Log v1.3

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0 (kickoff + Phase 0 audit), v1.1 (architecture pivot + D1 lock), v1.2 (D2 lock).

---

## v1.0 — Session kickoff (2026-04-27)

(See `MemPalace_Deployment_Session_Log_v1.0.md`. Phase 0 audit, Discovery Report v0.1, STOP gate.)

## v1.1 — Architecture pivot + D1 locked (2026-04-27)

(See `MemPalace_Deployment_Session_Log_v1.1.md`. Path A chosen: Coolify is single source of truth, palace at `~/.mempalace/palace` *inside the Coolify container*.)

## v1.2 — D2 locked (2026-04-27)

(See `MemPalace_Deployment_Session_Log_v1.2.md`. Bearer-token auth first, OAuth deferred to Phase 7.5+. Client wire-up order: Cowork → Claude Code → Claude Desktop → (later) Claude.ai web/mobile/voice.)

---

## v1.3 — D3 locked (2026-04-27)

### D3 — LOCKED: Four wings

**Corporate context:** MEGA is the parent corp. Interact (a.k.a. IEP — Interactive Event Productions) is the operating company that runs the events. Atlas is the software system Matt is developing to facilitate the businesses. No other subsidiaries warrant standalone wings — folders like Game Show, Catering, FNB, Warehouse are sub-operations *inside* Interact and become **rooms** under `wing_iep`.

**Wing list:**

| Wing | Purpose | Source content (rough) |
|---|---|---|
| `wing_mega` | Parent-corp content | Legal, intercompany decisions, holding-co governance, MEGA brand-level material |
| `wing_iep` | Event production operations | Vendors, venues, clients, timelines, productions, equipment, creative, event-technical, sub-ops (game show, catering, FNB, warehouse, waiver mgmt) |
| `wing_atlas` | Software / dev | Architecture decisions, code patterns, dev sessions, deployments, debugging — for the Atlas codebase and supporting infra |
| `wing_personal` | Non-business | Matt-personal content kept separate for scoped searches |

**Naming convention locked:** `wing_iep` (not `wing_interact`) — matches what the hardening notes and IEP halls in `config.py` already use. Future references in code, configs, and docs use `wing_iep`.

**Why four (not one, not seven):**

- One wing forfeits the +12% wing-filter retrieval boost and gives up tunnels entirely.
- Seven wings (each subsidiary functional area as its own wing) over-fragments — half would be near-empty and lose room-level differentiation.
- Four wings cleanly map onto Matt's actual mental model: "is this corporate, ops, code, or personal?"

**Tunnels expected to light up:**

- `wing_iep` ↔ `wing_atlas` on rooms like `vendor-coordination`, `event-management`, `cms`, `crm` (Atlas modules that touch event ops).
- `wing_mega` ↔ `wing_iep` on rooms like `legal-contracts`, `financial-reporting`.
- `wing_atlas` ↔ `wing_personal` minimal — clean separation desired.

**Implications for mining (Phases 3 and 4):**

- Mining `Claude Projects/` subdirectories needs explicit `--wing` flags so content lands in the right wing — defaults won't be smart enough.
  - Atlas-codebase-related folders (`Atlas CRM`, `Atlas Framework Documents`, `Architecture Documentation`, etc.) → `--wing wing_atlas`.
  - Event-ops folders (`Events App`, `Catering Documents`, `Game Show Files`, `FNB Tools`, `Waiver Management Documents`, `Warehouse`, `Marketing Content`) → `--wing wing_iep`.
  - Governance / corporate-level folders (`Governance Documents`, `Client Documentation`) → judgment call between `wing_mega` and `wing_iep`; default to `wing_iep` unless explicitly MEGA-corp content.
- The `C:\Users\phatt\Documents\GitHub\atlas\` codebase mining → `--wing wing_atlas`.
- The mempalace-fork itself, when dogfooded → `--wing wing_atlas` (it's a software project).

### Issues carried forward

- ISSUE-1 (open): Pytest 85/85 not re-verified — Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-4 (narrowed): HTTP MCP wrapper for Phase 7.
- ISSUE-5 (parked): voice-mode tool support — Matt testing externally.

### Versioning policy

Every artifact carries a version stamp. Decision locks bump session-log minor version. Each prior log version preserved as a rollback anchor.
