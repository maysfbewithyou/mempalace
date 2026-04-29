# MemPalace Deployment — Session Log v1.0

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies. build-tester applies. cowork-git-push applies for fork pushes.

---

## v1.0 — Session kickoff (2026-04-27)

### Phase 0 — Discovery audit (no installs)

- v0.1 — Read priority fork files: README.md (head), HARDENING_CHANGELOG.md (full), pyproject.toml, CONTRIBUTING.md, mempalace/cli.py, mempalace/config.py, hooks/mempal_save_hook.sh, hooks/mempal_precompact_hook.sh. Confirmed: 16 hardening fixes + 5 IEP personalizations are present in the working tree (config.py shows event-production wings, hooks have LF endings, pyproject pinned chromadb 0.5.23-0.6).
- v0.2 — Audited fork git state via .git plumbing files (git CLI hung under Windows-MCP — see Issues). Confirmed: HEAD on `main` at 252e440df5f8c13a7600d853fd54adbef6e59dbe; origin/main matches → hardening commits already pushed. Separate `security/hardening-v3` branch exists on origin (1f06c12...). upstream/main at 298143... Tags v3.0.0 and v3.1.0 present (from upstream lineage). Working tree was a fresh clone — no local commits ahead of origin/main. Untracked items: MemPalace_Cowork_Kickoff_v1.0.md, .pytest_cache/ (gitignored), pytest-cache-files-hzcavgs3/ (not gitignored).
- v0.3 — Audited host environment. Findings: Python 3.14.3 installed at `C:\Users\phatt\AppData\Local\Programs\Python\Python314\python.exe`; uv 0.11.3; node v24.14.0; coolify.interactep.app reachable (HTTP 200); github.com reachable. Disk free 83.9 GB. Issues found: (a) `python` on PATH resolves to a non-existent UV-managed cpython 3.13.12 — broken pointer; (b) `VIRTUAL_ENV` env var inherited from Windows-MCP points at a broken venv trampoline, which makes Python hang when invoked via `-c` or `-m` from this session; (c) `claude` CLI is NOT installed (no PATH match, no npm dir under AppData\Roaming\npm).
- v0.4 — Audited corpus to mine. Claude Projects: 12,361 MB across 1,542 files (Event Guy University alone is 11.5 GB — likely media, recommend skip). Atlas: 49.2 MB / 928 files (small, code-rich, prime mining target). mempalace-fork itself: 2.3 MB / 128 files. No Claude.ai chat exports or Slack exports found in standard locations.
- v0.5 — Wrote Discovery Report at `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\MemPalace_Phase_0_Discovery_v0.1.md`. STOP gate engaged — awaiting Matt's approval and D1–D9 decisions before Phase 1.

### Issues / open items

- ISSUE-1: Pytest regression gate (must be 85/85) was NOT executed in this Phase 0 because Python invocation hangs under Windows-MCP (broken `VIRTUAL_ENV` pointer + UV trampoline). Matt can run `py -3.14 -m pytest tests/ -v` directly in his own terminal, or we fix the venv pointer first. The hardening changelog claims 85/85 pass; we have not re-verified in this session.
- ISSUE-2: `claude` CLI not installed — blocks the Claude Code plugin install path (D2).
- ISSUE-3: `python` on PATH points at a missing UV-managed Python 3.13.12. Cosmetic — we have working Python via `py -3.14`.

### Versioning policy

Every artifact in this deployment carries a version stamp in the filename. Changes get a new minor version (v0.2 → v0.3) for rollback / reference. Major version bumps reserved for phase transitions or destructive changes.
