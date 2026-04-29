# MemPalace Deployment — Session Log v1.4

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.3.

---

## v1.0–v1.3 — Summary

(See `MemPalace_Deployment_Session_Log_v1.0.md` through `v1.3.md` for full entries.)

- v1.0: Phase 0 audit, Discovery Report v0.1, STOP gate.
- v1.1: D1 locked — Path A, Coolify single source of truth, palace at `~/.mempalace/palace` in container.
- v1.2: D2 locked — bearer-token auth first, OAuth deferred to Phase 7.5+.
- v1.3: D3 locked — four wings (`wing_mega`, `wing_iep`, `wing_atlas`, `wing_personal`).

---

## v1.4 — D4 locked (2026-04-27)

### D4 — LOCKED: Request fresh Claude.ai export, mine when it arrives

**Decision:** Matt will trigger a fresh Claude.ai data export via Settings → Privacy → Export data **now**, before Phase 7 finishes. Export ZIP arrives as a downloadable file (typically hours to a day or two). Mining the export does NOT block deployment — projects are mined first; conversations folded in when the file lands.

**Mining details when the export arrives:**

- Mode: `mempalace mine <unzipped path> --mode convos`
- Wing routing: most content lands in `wing_atlas` (development conversations) — but we should sample first to see if there are distinct event-production threads that should land in `wing_iep`. If the export is one mega-zip, we may need to split it by topic before mining (using `mempalace split` or manual filtering).
- Extraction strategy: `--extract general` (5-memory-type classification — decisions, preferences, milestones, problems, emotional context) gives richer indexing than the default exchange mode for retrospective conversation mining. Worth running on a sample first to compare results.

**Open questions parked until the export arrives:**

- Will exports include the long-running Claude Brain conversations (this is one of them)? If so, scope out PII/secret scanning before mining.
- Single wing or split by topic? Decide on inspection.

### Issues carried forward

- ISSUE-1 (open): Pytest 85/85 not re-verified — Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-4 (narrowed): HTTP MCP wrapper for Phase 7.
- ISSUE-5 (parked): voice-mode tool support — Matt testing externally.
- ISSUE-6 (NEW, parked): Claude.ai export ZIP awaited — Matt to trigger via Privacy settings. Track arrival; mine when it lands.

### Versioning policy

Every artifact carries a version stamp. Decision locks bump session-log minor version. Each prior log version preserved as a rollback anchor.
