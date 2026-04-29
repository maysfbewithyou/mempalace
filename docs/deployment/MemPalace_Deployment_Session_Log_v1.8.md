# MemPalace Deployment — Session Log v1.8

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.7.

---

## v1.0–v1.7 — Summary

- v1.0: Phase 0 audit, Discovery Report v0.1, STOP gate.
- v1.1: D1 — Path A, Coolify single source of truth.
- v1.2: D2 — bearer-token auth first.
- v1.3: D3 — four wings.
- v1.4: D4 — Claude.ai export requested.
- v1.5: D5 — Slack deferred to Phase 9.
- v1.6: D6 — Phase 8 closeout: tag + commit docs + delete stale branch.
- v1.7: D7 — Hybrid hooks with scheduled agentic review (weekly, Phase 6 wiring).

---

## v1.8 — D8 locked (2026-04-27)

### D8 — LOCKED: Monthly upstream sync + manual merges + agentic upstream-diff report

**Decision:** Pull from `upstream/main` on a **monthly cadence**, plus an immediate sync on any upstream major-version bump (`v3.x → v4.x`). All merges are **manual** — the hardening + IEP personalization layer is too sensitive to risk an auto-merge silently reverting a security fix or wing-config change.

**A scheduled task — analogous to D7's hook-review loop — runs monthly and produces an upstream-diff report:**

- Schedule: **first Monday of every month, 9:00 AM local.**
- Fetches `upstream`, computes the diff between `upstream/main` and our `origin/main`.
- **Categorizes** each upstream commit as:
  - **CONFLICT-RISK** — touches a file we've modified in our hardening or personalization passes (file list below). Needs human review before merge.
  - **SAFE FAST-FORWARD** — touches files we've never modified. Still requires human approval, but lower risk.
  - **NOTEWORTHY** — major version bump, README rewrites, new MCP tools, or anything affecting the public API of the package.
- Report path: `~\.mempalace\reports\upstream-diff-YYYY-MM-DD.md`.
- Notification escalation: if any upstream commit lands a security CVE fix or addresses a known issue we've personalized around, escalates to HIGH severity (file marker + future Slack post).

**Files we've modified (auto-flag CONFLICT-RISK on any upstream change to these):**

- `mempalace/mcp_server.py` (Fixes 1, 10, 12, 13, 15; Personalization 2)
- `mempalace/hooks_cli.py` (Fixes 5, 6, 7, 11, 14; Personalization 3)
- `mempalace/config.py` (Personalization 1)
- `mempalace/query_sanitizer.py` (Fix 1 — NEW file we added)
- `mempalace/normalize.py` (Fix 8)
- `mempalace/room_detector_local.py` (Personalization 4)
- `mempalace/general_extractor.py` (Personalization 5)
- `pyproject.toml` (Fix 2)
- `hooks/mempal_save_hook.sh`, `hooks/mempal_precompact_hook.sh` (Fix 3, 9)
- `.claude-plugin/hooks/*.sh`, `.codex-plugin/hooks/*.sh` (Fix 4, 9)
- `tests/test_hooks_cli.py` (Fix 16)

**Why monthly and not weekly:**

- Upstream activity isn't weekly-paced — they ship in bursts.
- A month of accumulated commits in a tight diff is easier to grok than 4 weekly diffs.
- Major-bump trigger ensures we don't sit on important changes for up to 4 weeks.

**Why all merges manual (no auto-merge of "safe" fast-forwards):**

- A file we don't currently modify could become a file we *should* modify in a future hardening pass. Auto-merging "safe" upstream commits trains the wrong reflex.
- The hardened fork is small (16 fixes, 5 personalizations); manual review of upstream commits across the whole tree takes minutes per month, not hours.
- Catching a regression in a hardening fix the moment it lands beats catching it in production.

**Implementation:** the upstream-diff scheduled task is wired during Phase 6 alongside the hook-review task (using `anthropic-skills:schedule`). Both run at the same Monday 9 AM slot for tidy weekly/monthly governance review.

### Issues carried forward

- ISSUE-1 (open): Pytest 85/85 not re-verified — Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-4 (narrowed): HTTP MCP wrapper for Phase 7.
- ISSUE-5 (parked): voice-mode tool support — Matt testing externally.
- ISSUE-6 (parked): Claude.ai export ZIP awaited.
- ISSUE-7 (parked): Slack mining — Phase 9.
- ISSUE-8 (Phase 6): Verify Stop hook merge behavior.

### Versioning policy

Every artifact carries a version stamp. Decision locks bump session-log minor version. Each prior log version preserved as a rollback anchor.
