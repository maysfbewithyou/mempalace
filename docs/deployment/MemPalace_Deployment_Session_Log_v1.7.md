# MemPalace Deployment — Session Log v1.7

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.6.

---

## v1.0–v1.6 — Summary

- v1.0: Phase 0 audit, Discovery Report v0.1, STOP gate.
- v1.1: D1 — Path A, Coolify single source of truth.
- v1.2: D2 — bearer-token auth first.
- v1.3: D3 — four wings: `wing_mega`, `wing_iep`, `wing_atlas`, `wing_personal`.
- v1.4: D4 — Claude.ai export requested, mine when arrives.
- v1.5: D5 — Slack deferred to Phase 9.
- v1.6: D6 — Phase 8 closeout: tag + commit docs + delete stale branch.

---

## v1.7 — D7 locked (2026-04-27)

### D7 — LOCKED: Hybrid hook scope with scheduled agentic review

**Decision:** Install hooks in a **hybrid scope** — user-global Stop+PreCompact for broad coverage, project-level overrides for higher-frequency saves on key repos. A **scheduled task** runs a periodic agentic review of hook behavior + palace growth + drawer quality and recommends tuning. The schedule task is a self-tuning governance loop, so we don't lock the save-interval policy in stone — we let data drive it.

**Hook configuration (initial defaults — subject to scheduled-review tuning):**

| Layer | Hook | Save interval | Path |
|---|---|---|---|
| User-global | Stop | **30** human messages | `~\.claude\settings.json` |
| User-global | PreCompact | always-block | `~\.claude\settings.json` |
| Project override (high-value) | Stop | **15** | `<project>\.claude\settings.local.json` |
| Project override | PreCompact | inherits user-global | (no override needed) |

**Initial high-value projects (Stop interval = 15):**

- `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\` — dogfood the palace's own dev work.
- `C:\Users\phatt\Documents\GitHub\atlas\` — Atlas dev decisions.
- `C:\Users\phatt\Documents\Claude\Projects\Claude Brain\` — this Cowork session's working folder.

(Add more later by dropping a `.claude/settings.local.json` in the relevant project.)

**Why hybrid over pure-global or pure-project:**

- Pure-global on save-interval=15 floods the palace with throwaway-session noise.
- Pure-project misses ad-hoc Code sessions where Matt has a real insight worth saving.
- PreCompact MUST fire everywhere — compaction loses context, and we always want a save before that. Hence PreCompact at user-global.
- High-value project overrides give signal-rich content the higher-frequency capture it deserves.

**Scheduled review task (the agentic governance loop):**

A scheduled task runs periodically — proposed cadence **weekly, Monday 9:00 AM local** — that:

1. Reads `~\.mempalace\hook_state\hook.log` for the past 7 days. Counts triggers per session, aborted saves, sessions where the AI didn't actually save when blocked.
2. Pulls palace stats (drawer count by wing, growth rate, hall distribution) via the MCP.
3. Samples 5 recent drawers per wing and assesses quality (verbatim-ness, signal density, room routing accuracy).
4. Produces a markdown report at `~\.mempalace\reports\hook-review-YYYY-MM-DD.md` with recommendations: raise/lower SAVE_INTERVAL globally or per-project, add/remove project overrides, flag wings that are over- or under-filled.
5. Optionally, if recommendation severity is HIGH, surfaces a notification (file marker, system notification, or future Slack post).

**Scheduling:** to be created during Phase 6 (Hook wiring) using the `anthropic-skills:schedule` skill. Cadence and report format can be revised at that time.

**Phase 6 implementation order:**

1. Confirm Claude Code's Stop+PreCompact hook merge behavior (do user-global and project-local both fire? does the more-specific override the global? — needs verification before wiring).
2. Wire user-global hooks first.
3. Add project-level overrides on the three high-value repos.
4. Create scheduled review task.
5. Verify by running a dummy session in each scoped project and reading `hook.log`.

### Open question carried into Phase 6

- **Stop hook merge behavior:** Claude Code may run BOTH user-global and project-local Stop hooks if both are defined, leading to double-blocks and potential infinite-loop edge cases. Needs a 5-minute experiment before committing the hybrid layout. Fallback: pure user-global with a per-folder save-interval lookup baked into the hook script itself.

### Issues carried forward

- ISSUE-1 (open): Pytest 85/85 not re-verified — Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-4 (narrowed): HTTP MCP wrapper for Phase 7.
- ISSUE-5 (parked): voice-mode tool support — Matt testing externally.
- ISSUE-6 (parked): Claude.ai export ZIP awaited.
- ISSUE-7 (parked): Slack mining — Phase 9.
- ISSUE-8 (NEW, Phase 6): Verify Stop hook merge behavior before installing hybrid scope.

### Versioning policy

Every artifact carries a version stamp. Decision locks bump session-log minor version. Each prior log version preserved as a rollback anchor.
