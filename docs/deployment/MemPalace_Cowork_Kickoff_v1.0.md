# MemPalace Deployment — Cowork Kickoff Prompt (v1.0)

**Compiled:** 2026-04-27
**Project:** MemPalace fork — IEP-personalized AI memory system
**Goal:** Deploy the existing forked + hardened MemPalace so Claude has a persistent, searchable brain across all IEP / Atlas / event-production work.
**Workspace:** `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`

---

## How to use this file

1. Open a fresh Cowork session.
2. Point the project at `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`.
3. Copy everything inside the fenced block at the bottom of this file.
4. Paste it as your first message.
5. Cowork should respond with a Phase 0 Discovery Report and a list of decisions it needs from you before installing anything.

---

## Background — what's already done (the part you keep forgetting because Cowork wiped)

You and Claude already did the hard part. Specifically:

**The fork** — `https://github.com/maysfbewithyou/mempalace.git` (origin, branch `main`), forked from `https://github.com/MemPalace/mempalace.git` (upstream). MemPalace is an OSS Python package by milla-jovovich described as *"Give your AI a memory."* It stores conversations and project files into a ChromaDB-backed "palace" with wings (people/projects), halls (memory types — facts, events, discoveries, preferences, advice), rooms (specific topics), and drawers (verbatim source files). 96.6% R@5 on LongMemEval in raw mode. Local, free, zero API.

**The hardening pass** — captured in `HARDENING_CHANGELOG.md` at the repo root. Two versions, both 2026-04-09:

- **Version 1.0 — Security hardening (9 fixes):** Query sanitizer for AI-prepended system prompts (PR #385 adaptation), tightened ChromaDB pin to `>=0.5.23,<0.6`, precompact hook session ID sanitization, codex plugin hook name whitelist, MEMPAL_DIR env var hardening (must be under $HOME), hook log rotation (5 MB / 3 backups), restrictive 0o700/0o600 permissions on state files, Claude.ai normalizer field detection (handles `sender`/`text`/`body` variants), and CRLF→LF normalization for shell hooks.

- **Version 2.0 — Deep audit + IEP personalization (7 fixes + 5 personalizations):** Input validation on ALL read-path MCP parameters (was inconsistent with writes), TOCTOU race fix in hook state files via atomic writes, drawer ID format regex, knowledge graph sanitization gap closed (kg_invalidate / kg_query / kg_timeline / date params), MEMPAL_DIR `/tmp` allowance removed, numeric parameter bounds checking (limit 1-50, max_hops 1-10, threshold 0-1, last_n 1-100), and test suite updated (all 85 tests still pass).

  Personalizations: **wings** retargeted to event-production categories (`events`, `venues`, `vendors`, `timelines`, `budgets`, `team`, `clients`, `productions`, `equipment`, `creative`, `technical`); AAAK dialect updated with event-specific entity codes; hook STOP/PRECOMPACT messages tell the AI to save *venue decisions, vendor updates, timeline changes, budget approvals, client preferences, equipment specs, production notes*; 40+ folder→room pattern mappings (e.g. `vendor`/`caterer`/`contracts` → `vendor-coordination`); content extractor markers for venue selection, contract signing, load-in done, etc.

So the code is forked, hardened, personalized, and tested. **What's missing is deployment.** We never finished installing it as a working memory system Claude could actually call into.

---

## Why this matters for IEP

The point of MemPalace, in your own words: *"help Claude have a better brain about what we do and how we do it."* Today, every Claude session starts cold — the Production Schedule Builder PRD, the LA Fairgrounds subcontractor history, Tim's quirks, Luke's Coolify setup, the 9-category TCL governance — none of it persists. You re-explain it every chat.

With MemPalace deployed, Claude (in Code, in Cowork, in Chat via MCP, or in any other MCP-compatible client) can call `mempalace_search "what did we decide about the LA Fairgrounds revenue split"` and get verbatim chunks from the actual conversation back. No summarization, no API cost, no cloud.

---

## Scope of this Cowork session

**In scope:**
1. Verify the fork's current state (git status, hardening commits pushed?, tests still pass)
2. Decide consumption pattern (which clients connect — Claude Code, Cowork, Chat-via-MCP)
3. Install dependencies (Python 3.9+, ChromaDB 0.5.23, PyYAML 6.0.2)
4. Run `mempalace init` to set up Matt's personal palace (`~/.mempalace/`)
5. Mine the existing IEP corpus into the palace (Atlas docs, Slack exports, past Claude exports)
6. Wire auto-save hooks (Save + PreCompact) into Claude Code
7. Optional: stand up the MCP server as a Coolify service so Cowork and Chat can also reach it
8. Verify with a real query — ask MemPalace something only the corpus would know

**Out of scope:**
- Modifying upstream MemPalace code (the fork is already hardened — leave it)
- Atlas Pre-Push Review process (this is not Atlas — it's Matt's personal tooling)
- Pushing changes upstream to `MemPalace/mempalace` (we may or may not, but it's a separate decision)
- Building any new features into MemPalace itself

---

## Governance prerequisites

This is **NOT an Atlas build**, so the 9-category Atlas Delivery Standard does not apply. However:

- **Versioning protocol** still applies — `..\.claude\references\versioning.md`. Every change tracked, every rollback anchored.
- **Build-tester skill** applies — run the existing 85-test suite as the regression gate after every change.
- **cowork-git-push skill** applies for any push to `maysfbewithyou/mempalace`. Notification channel: `#atlas-updates` (since this is internal IEP tooling).
- **No Atlas TCL** — but **do** maintain a session-scoped log called `MemPalace_Deployment_Session_Log_v1.0.md` in this folder, with timestamped entries for every install / config / mining run.

---

## Skills to invoke

| Skill | When |
|---|---|
| `build-tester` | After dependency install (Light Test) and after each mining run (Light Test) |
| `cowork-git-push` | Only if we end up committing changes to the fork (e.g., a v3.0 personalization tweak) |
| **NOT** `atlas-delivery-standard` | This is not Atlas |
| **NOT** `atlas-pre-push-review` | This is not Atlas |

---

## Phase 0 — your first task (do not install anything yet)

1. **Read the listed source files in order:**
   - `README.md` — full project overview, install paths, MCP tool list, AAAK explanation
   - `HARDENING_CHANGELOG.md` — every fix and personalization already applied (16 + 5)
   - `pyproject.toml` — confirm Python ≥3.9, ChromaDB pin, PyYAML pin
   - `CONTRIBUTING.md` — test command, project structure
   - `mempalace/cli.py` — entry points (so you know which commands work)
   - `mempalace/mcp_server.py` — the 19 MCP tools (skim — full read deferred)
   - `mempalace/config.py` — confirm event-production wings are wired in
   - `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh` — confirm Unix LF endings, sanitization

2. **Audit the fork's current state:**
   - Run `git status` — any uncommitted hardening work?
   - Run `git log --oneline -30` — confirm the 16+5 hardening commits are present
   - Run `git remote -v` — confirm both `origin` (maysfbewithyou) and `upstream` (MemPalace)
   - Run `git fetch upstream && git log HEAD..upstream/main --oneline` — has upstream moved since the fork?
   - Run `git push origin main --dry-run` — are the hardening commits pushed to GitHub yet, or only local?

3. **Audit the host environment:**
   - Python version (`python --version` and `python3 --version`) — need ≥3.9
   - Pip available, virtualenv/uv available
   - Available disk for ChromaDB (the palace will grow — 22k drawers ≈ a few hundred MB)
   - Whether Claude Code is installed and accessible (`claude --version`)
   - Whether Coolify is reachable from this VM (it lives at `coolify.interactep.app`)

4. **Audit the corpus to mine:**
   - List candidate source folders for mining:
     - `C:\Users\phatt\Desktop\Claude Workspace\Claude Projects\` (Atlas docs, PRDs)
     - `C:\Users\phatt\Documents\GitHub\atlas\` (the actual codebase — skip `node_modules` and `.next`)
     - `C:\Users\phatt\Desktop\Cowork_Backup_2026-04-16_11-52\` (the VHDX is too binary; skip the file itself but reference its existence)
     - Any folder of Claude.ai chat exports if Matt has them
     - Any Slack exports if Matt has them
   - For each, give a rough size estimate and a recommended mining mode (`projects` / `convos` / `general`)

5. **Produce a Phase 0 Discovery Report** as `MemPalace_Phase_0_Discovery_v0.1.md` in this folder, covering:
   - Git state (commits ahead of upstream? pushed to origin?)
   - Environment readiness (Python, pip, disk)
   - Test result from `pytest tests/ -v` — confirm 85/85 still pass before any deployment
   - Corpus inventory with size estimates and recommended modes
   - Recommended consumption pattern (Claude Code plugin? MCP-add command? Coolify-hosted MCP service?)
   - Decisions list for Matt (see "Open Decisions" below)

6. **Stop and wait for Matt's approval** of the Discovery Report before starting Phase 1.

---

## Proposed phase plan (refine in Discovery Report)

| Phase | Scope | Deliverables |
|---|---|---|
| **0** | Discovery + plan | `MemPalace_Phase_0_Discovery_v0.1.md`, Matt approval |
| **1** | Install + verify | `pip install -e .` in a venv, `pytest tests/ -v` confirms 85/85, version tag `v0.1.0-deploy` on the deployment session log |
| **2** | Initialize palace | `mempalace init ~/projects/iep` — palace path, wing config, identity.txt; commit any IEP-specific config files to a new `iep-config/` folder in the fork |
| **3** | First mining run | Mine `Claude Workspace\Claude Projects\` in `projects` mode; verify with a search; report drawer count and wing distribution |
| **4** | Second mining run | Mine the Atlas codebase in `projects` mode; verify cross-wing tunnels exist (e.g., `auth-migration` should bridge personal and project wings) |
| **5** | Connect to Claude Code | Run `claude plugin marketplace add maysfbewithyou/mempalace` and `claude plugin install --scope user mempalace`. Verify `/skills` shows `mempalace`. Run a real query end-to-end. |
| **6** | Wire auto-save hooks | Configure `Stop` and `PreCompact` hooks in Claude Code settings.json, pointing at `hooks/mempal_save_hook.sh` and `hooks/mempal_precompact_hook.sh`. Set `MEMPAL_DIR` env var to `~/projects/iep`. |
| **7** | Optional Cowork connectivity | Stand up `python -m mempalace.mcp_server` as a long-running service in Coolify (or as a Windows scheduled task); expose over Cloudflare Tunnel at `mempalace.tstly.dev`; configure as remote MCP in Cowork settings if/when Cowork supports remote MCP. **Skip if remote MCP is not yet supported in Cowork** — defer to Phase 8. |
| **8** | Push hardening commits to origin (if not already) | Use `cowork-git-push` skill. Slack notify `#atlas-updates`. Tag `v3.0.14-iep-hardened` on the fork. |

---

## Open Decisions (surface back to Matt at end of Phase 0)

| # | Decision | Why it matters |
|---|---|---|
| D1 | **Palace location.** Default is `~/.mempalace/palace` — keep, or override to `C:\Users\phatt\Desktop\Claude Workspace\.mempalace\` for visibility alongside other workspace artifacts? | Affects backup strategy, Filesystem MCP visibility, and whether the palace gets caught in any future workspace sweeps. |
| D2 | **Consumption pattern.** Claude Code plugin only / MCP-add via stdio for Code only / Cowork-reachable HTTP wrapper / all of the above? | Ties to whether Phase 7 happens. |
| D3 | **First wing assignments.** `wing_iep`, `wing_mega`, `wing_atlas` as separate wings, or one `wing_iep` covering all three brands? | Affects search filtering. Recommend three wings since IEP, Mega, and Atlas-the-platform are separable concerns. |
| D4 | **Mining mode for chat exports.** Matt — do you have Claude.ai exports? If yes, `convos` mode. If no, skip until you generate them. | Cold-starting the palace from project docs alone gives weak retrieval on past *decisions*. Chat exports are the goldmine. |
| D5 | **Slack export.** Same question — do you have a Slack export? Worth pulling? | `#atlas-updates` and DMs with Luke contain a huge amount of operational context the palace would benefit from. |
| D6 | **Hardening commits visibility.** Do you want the fork pushed publicly to your GitHub user `maysfbewithyou`, or kept local? | If pushed, you can `claude plugin install` from your fork directly. If local, install path is `pip install -e .` from the local clone. |
| D7 | **Auto-save scope.** Hooks fire on every Claude Code session-end. Do you want auto-save on **all** sessions, or only specific projects (Atlas / IEP / personal)? | Affects palace bloat. Recommend project-scoped at first. |
| D8 | **Upstream sync cadence.** MemPalace upstream is active (the README's "Note from Milla & Ben" lists ongoing fixes). Sync upstream weekly, monthly, or only on major version bumps? | Affects how stale the fork gets. Recommend monthly with build-tester gating each merge. |
| D9 | **Identity layer (`~/.mempalace/identity.txt`).** This is the ~50-token Layer 0 that loads on every wake-up. What goes in it? | Recommend: name, role at IEP, primary projects, communication style preferences (concise, no emoji), governance rules (versioning, no Supabase). |

---

## Stack constraints (sanity check)

- **Python ≥3.9** — confirmed in `pyproject.toml`
- **Dependencies:** ChromaDB 0.5.23-0.5.x, PyYAML 6.0.2-6.x — both pinned tight after the v1.0 hardening
- **No external APIs required** — by design. The 96.6% benchmark is from raw mode with zero API calls.
- **No Atlas stack overlap** — MemPalace runs in its own venv. It does NOT use Flask, SQLAlchemy, Alembic, Postgres, Coolify, Strapi, Whisper, Resend, or node-cron. The only intersection is that the MemPalace MCP server *could* be deployed to Coolify alongside Atlas services, but that's optional (Phase 7).

---

## Files NOT to touch this session

- Anything in `C:\Users\phatt\Documents\GitHub\atlas\` (this is Atlas, separate codebase)
- Anything in `C:\Users\phatt\Desktop\Claude Workspace\Claude Projects\` (these are Atlas project docs — readable for mining, but no edits)
- The upstream `MemPalace/mempalace` repo (we're working on the fork only)
- The `Cowork_Backup_2026-04-16_11-52` VHDX file (it's a 6.4 GB ext4 image — irrelevant to this work)

---

## Paste this into Cowork

```
MEMPALACE DEPLOYMENT — SESSION KICKOFF v1.0

You are picking up the deployment of the IEP-personalized MemPalace fork. The code is forked, hardened (16 security fixes + 5 IEP personalizations across two passes on 2026-04-09), and sitting at C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\. Tests pass (85/85 per HARDENING_CHANGELOG.md). What's missing is the actual deployment.

═══════════════════════════════════════════════
PROJECT IDENTITY
═══════════════════════════════════════════════

- Project: MemPalace fork — IEP-personalized AI memory system
- Origin (Matt's fork): https://github.com/maysfbewithyou/mempalace.git, branch main
- Upstream: https://github.com/MemPalace/mempalace.git
- Local working tree: C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\
- Why this exists: give Claude a persistent, searchable brain across all IEP / Atlas / event-production work, replacing the per-session cold-start.
- This is NOT Atlas. Atlas governance does not apply. This is Matt's personal tooling.

═══════════════════════════════════════════════
MEMPALACE IN ONE PARAGRAPH
═══════════════════════════════════════════════

OSS Python package, ChromaDB-backed, MIT licensed, by milla-jovovich. Stores conversations and project files into a "palace" with wings (people/projects), halls (memory types), rooms (specific topics), and drawers (verbatim source files). 96.6% R@5 on LongMemEval in raw mode, zero API calls, fully local. Has 19 MCP tools, Claude Code plugin, hooks for auto-save. The fork has been personalized for event production: wings, halls, room patterns, and AAAK protocol all retargeted at venues / vendors / timelines / budgets / clients / productions / equipment / creative / technical.

═══════════════════════════════════════════════
GOVERNANCE FOR THIS SESSION
═══════════════════════════════════════════════

- Versioning protocol applies — see C:\Users\phatt\Desktop\Claude Workspace\.claude\references\versioning.md
- build-tester skill applies — run pytest tests/ -v as the regression gate after every change
- cowork-git-push skill applies if and only if we commit to the fork
- atlas-delivery-standard does NOT apply (not Atlas)
- atlas-pre-push-review does NOT apply (not Atlas)
- Maintain a session log: MemPalace_Deployment_Session_Log_v1.0.md in the project folder

═══════════════════════════════════════════════
PHASE 0 — DO THIS FIRST, NO INSTALLS YET
═══════════════════════════════════════════════

1. Read these files in this order:
   - README.md (full overview)
   - HARDENING_CHANGELOG.md (every fix and personalization already applied)
   - pyproject.toml (deps and pins)
   - CONTRIBUTING.md (test command, structure)
   - mempalace/cli.py (entry points)
   - mempalace/mcp_server.py (skim — 19 tools)
   - mempalace/config.py (confirm event wings present)
   - hooks/mempal_save_hook.sh and hooks/mempal_precompact_hook.sh (LF endings, sanitization)

2. Audit fork state:
   - git status
   - git log --oneline -30
   - git remote -v
   - git fetch upstream and git log HEAD..upstream/main --oneline
   - git push origin main --dry-run (are hardening commits pushed?)

3. Audit host environment:
   - python / python3 version (need ≥3.9)
   - pip, uv, virtualenv availability
   - Available disk
   - claude --version (Claude Code installed?)
   - Reachability of coolify.interactep.app

4. Audit the corpus to mine:
   - C:\Users\phatt\Desktop\Claude Workspace\Claude Projects\ — mode: projects
   - C:\Users\phatt\Documents\GitHub\atlas\ — mode: projects (skip node_modules, .next, .git)
   - Any Claude.ai chat exports Matt may have — mode: convos
   - Any Slack exports — mode: convos
   - Estimate sizes per source

5. Produce MemPalace_Phase_0_Discovery_v0.1.md in this folder. Cover:
   - Git state (ahead of upstream? pushed to origin?)
   - Environment readiness
   - pytest tests/ -v result (must be 85/85 before proceeding)
   - Corpus inventory with sizes and recommended modes
   - Recommended consumption pattern (Code plugin / MCP-add / Coolify service / all)
   - Decisions list for Matt (the 9 D1-D9 items below)

6. STOP. Wait for Matt's approval before starting Phase 1.

═══════════════════════════════════════════════
DECISIONS NEEDED FROM MATT (surface in Discovery Report)
═══════════════════════════════════════════════

D1. Palace location: ~/.mempalace/palace (default) or C:\Users\phatt\Desktop\Claude Workspace\.mempalace\ ?
D2. Consumption: Claude Code plugin / MCP-add stdio / Coolify-hosted HTTP wrapper / all?
D3. Wings: separate wing_iep, wing_mega, wing_atlas, or one combined wing?
D4. Claude.ai chat exports — does Matt have them? If yes, mining mode is convos.
D5. Slack export — does Matt have one? Recommended to mine.
D6. Push hardening commits to GitHub origin, or keep local-only?
D7. Auto-save hooks — fire on all Code sessions or only specific projects?
D8. Upstream sync cadence — weekly / monthly / on major versions?
D9. Identity layer (~/.mempalace/identity.txt) content — what should the always-loaded ~50 tokens say?

═══════════════════════════════════════════════
PROPOSED PHASE PLAN (refine in Discovery Report)
═══════════════════════════════════════════════

Phase 1: Install + verify (venv, pip install -e ., pytest must pass 85/85)
Phase 2: mempalace init — wing config, identity.txt
Phase 3: Mine Claude Projects/ in projects mode, verify with a search
Phase 4: Mine atlas codebase in projects mode, verify cross-wing tunnels
Phase 5: Connect to Claude Code (plugin install), run real end-to-end query
Phase 6: Wire Save + PreCompact hooks, set MEMPAL_DIR
Phase 7: Optional — stand up MCP server on Coolify, expose via Cloudflare Tunnel at mempalace.tstly.dev (skip if Cowork doesn't yet support remote MCP)
Phase 8: Push hardening commits to origin via cowork-git-push, tag v3.0.14-iep-hardened

═══════════════════════════════════════════════
CONSTRAINTS / DON'T-TOUCH LIST
═══════════════════════════════════════════════

- Do NOT modify upstream MemPalace code; the fork is already hardened
- Do NOT touch C:\Users\phatt\Documents\GitHub\atlas\ (separate codebase, different governance)
- Do NOT touch C:\Users\phatt\Desktop\Claude Workspace\Claude Projects\ except read-only for mining
- Do NOT touch the Cowork_Backup_2026-04-16_11-52 VHDX (irrelevant binary blob)

When Phase 0 deliverables are saved, return:
  - Path to the Discovery Report
  - pytest result (must be 85/85)
  - Git state summary (commits ahead of upstream, pushed to origin yes/no)
  - List of D1–D9 with your recommended default for each
```

---

## Version history

- **v1.0 (2026-04-27)** — Initial kickoff for MemPalace fork deployment after Matt confirmed the project is the mempalace-fork (originally referred to as "mywiki" in chat). Built from on-disk fork state, HARDENING_CHANGELOG.md, README, and pyproject.toml. No prior kickoff existed.
