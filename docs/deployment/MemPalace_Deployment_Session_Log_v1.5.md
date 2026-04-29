# MemPalace Deployment — Session Log v1.5

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.4.

---

## v1.0–v1.4 — Summary

- v1.0: Phase 0 audit, Discovery Report v0.1, STOP gate.
- v1.1: D1 locked — Path A, Coolify single source of truth.
- v1.2: D2 locked — bearer-token auth first, OAuth deferred.
- v1.3: D3 locked — four wings (`wing_mega`, `wing_iep`, `wing_atlas`, `wing_personal`).
- v1.4: D4 locked — request fresh Claude.ai export now, mine when it arrives.

---

## v1.5 — D5 locked (2026-04-27)

### D5 — LOCKED: Slack integration deferred to Phase 9 (post-v1.0)

**Decision:** Slack export and mining are **out of scope** for the initial v1.0 deployment. The team's Slack history will be addressed as a post-launch follow-up (designated Phase 9) once the hosted MemPalace is stable, dogfooded, and serving Matt's day-to-day work reliably.

**Why defer rather than skip:**

- The IEP team likely runs meaningful operational decisions through Slack (vendor conversations, day-of cues, post-mortems). Skipping outright would forfeit a high-signal corpus.
- But Slack mining adds scope risk to v1.0: workspace export approval, public vs private vs DM scoping, sensitivity filtering, selective-channel export logistics. None of that is core to standing up the hosted palace.
- Deferring keeps v1.0 tight while preserving the option.

**Phase 9 scope (parked, to be re-opened post-v1.0):**

- Confirm Matt's workspace export rights and team policy on chat archival.
- Decide scope: whole-workspace vs selective-channels vs public-only.
- PII / sensitive-content scan before mining.
- Wing routing (likely all `wing_iep`, since Slack is operational).
- Extraction mode: `--extract general` recommended.

### Issues carried forward

- ISSUE-1 (open): Pytest 85/85 not re-verified — Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-4 (narrowed): HTTP MCP wrapper for Phase 7.
- ISSUE-5 (parked): voice-mode tool support — Matt testing externally.
- ISSUE-6 (parked): Claude.ai export ZIP awaited.
- ISSUE-7 (NEW, parked): Slack mining design — re-opens at Phase 9.

### Phase plan adjustment

The kickoff's 8-phase plan is extended:

- Phases 1–8 → v1.0 deployment (initial hosted MemPalace, mining of projects + Atlas + Claude.ai export when it arrives).
- **Phase 9 (post-v1.0)** → Slack mining design + execution.
- (Future) **Phase 10** → OAuth wrapper for claude.ai web/mobile/voice clients (was Phase 7.5).
- (Future) **Phase 11+** → other follow-ups as they surface.

### Versioning policy

Every artifact carries a version stamp. Decision locks bump session-log minor version. Each prior log version preserved as a rollback anchor.
