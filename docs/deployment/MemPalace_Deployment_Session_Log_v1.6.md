# MemPalace Deployment — Session Log v1.6

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.5.

---

## v1.0–v1.5 — Summary

- v1.0: Phase 0 audit, Discovery Report v0.1, STOP gate.
- v1.1: D1 — Path A, Coolify single source of truth.
- v1.2: D2 — bearer-token auth first, OAuth deferred.
- v1.3: D3 — four wings: `wing_mega`, `wing_iep`, `wing_atlas`, `wing_personal`.
- v1.4: D4 — request fresh Claude.ai export now, mine when it arrives.
- v1.5: D5 — Slack deferred to Phase 9.

---

## v1.6 — D6 locked (2026-04-27)

### D6 — LOCKED: Phase 8 closeout — tag + commit docs + clean stale branch

**Decision:** All three closeout actions execute in Phase 8 of v1.0.

**Phase 8 actions, in order:**

1. **Move deployment docs into `docs/deployment/`** subfolder (Kickoff doc, Discovery Report v0.1, Session Log series v1.0–vN, plus any architecture docs we generate). Commit them under a clear conventional-commit message: `docs: deployment session artifacts (v1.0)`.
2. **Tag `main` as `v3.0.14-iep-hardened`** and push the tag. Annotated tag (not lightweight) with a message summarizing: 16 hardening fixes + 5 IEP personalizations + four-wing config. This is the rollback anchor for "post-deployment, pre-mining-experiments."
3. **Delete stale `security/hardening-v3` branch on origin** via `git push origin --delete security/hardening-v3`. The tag is a cleaner anchor.
4. **Optionally** also tidy the `pytest-cache-files-hzcavgs3/` stale dir — either delete it or add to `.gitignore`. Trivial.

**Why commit the docs (not gitignore them):**

- Versioned rollback anchors are exactly what Matt's preferences ask for. Files in git get the strongest version control.
- The fork is Matt's, so visibility is fine.
- Future-Matt opening the repo a year from now sees the deployment lineage intact.

**Implications for earlier phases:**

- The session log files Windows-MCP is writing this session are *staged* outside git history. Phase 8 is when they enter the repo. Until then, treat them as untracked work-in-progress.
- The kickoff doc Matt placed in the root (`MemPalace_Cowork_Kickoff_v1.0.md`) gets moved (not deleted) to `docs/deployment/` in Phase 8. Its filename is preserved.

### Issues carried forward

- ISSUE-1 (open): Pytest 85/85 not re-verified — Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-4 (narrowed): HTTP MCP wrapper for Phase 7.
- ISSUE-5 (parked): voice-mode tool support — Matt testing externally.
- ISSUE-6 (parked): Claude.ai export ZIP awaited.
- ISSUE-7 (parked): Slack mining design — re-opens at Phase 9.

### Versioning policy

Every artifact carries a version stamp. Decision locks bump session-log minor version. Each prior log version preserved as a rollback anchor.
