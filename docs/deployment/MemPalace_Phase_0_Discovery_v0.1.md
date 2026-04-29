# MemPalace Deployment — Phase 0 Discovery Report (v0.1)

Date: 2026-04-27
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: `https://github.com/maysfbewithyou/mempalace.git` (branch `main`)
Upstream: `https://github.com/MemPalace/mempalace.git`

> **Phase 0 is read-only.** No installs, no test runs, no commits. This report is the gate before Phase 1 begins.

---

## 1. Headline status

| Check | State |
|---|---|
| Hardening fixes present in working tree | YES — 16 fixes + 5 IEP personalizations all visible in source |
| Hardening commits pushed to `origin/main` | YES — local main = origin/main = `252e440df5f8c13a7600d853fd54adbef6e59dbe` |
| Local commits ahead of origin | NONE — working tree is a fresh clone, no local commits |
| Local commits ahead of `upstream/main` | YES (by definition — fork carries hardening) |
| Working tree clean | Effectively yes; only untracked items are the kickoff doc and pytest caches |
| pytest 85/85 re-verified this session | **NO** — see ISSUE-1 below. Changelog claims 85/85; not re-run in this Phase 0. |
| Host Python ≥ 3.9 | YES (Python 3.14.3 installed) |
| `claude` CLI installed | **NO** — blocks Claude Code plugin path until installed |
| `coolify.interactep.app` reachable | YES (HTTP 200) |
| Disk free | 83.9 GB on C: |

---

## 2. Git state (read via .git plumbing — git CLI hung under Windows-MCP, see ISSUE-1)

Local refs:

- `HEAD` → `refs/heads/main` → `252e440df5f8c13a7600d853fd54adbef6e59dbe`
- Tags: `v3.0.0` (`1782628b...`), `v3.1.0` (`731531f8...`) — both inherited from upstream lineage
- No local-only branches; no local commits beyond clone

Remotes:

- `origin` = `https://github.com/maysfbewithyou/mempalace.git`
  - `origin/main` = `252e440df5f8c13a7600d853fd54adbef6e59dbe` (same as local `main` → already pushed)
  - `origin/security/hardening-v3` = `1f06c129625a12307e9086b53b6618454a532298` (separate working branch; presumably the branch the hardening was originally done on, then merged into main)
- `upstream` = `https://github.com/MemPalace/mempalace.git`
  - `upstream/main` = `298143353509ceeb27941fe6f3bb7e677e3c6264` (different commit — fork is ahead of upstream by hardening commits)

Conclusion: `main` is fully synced with origin. The hardening work is already public on Matt's fork. The only remaining "git" task in Phase 8 is to create and push a tag (e.g. `v3.0.14-iep-hardened`), since no tag for the hardened state currently exists.

Untracked items in working tree (presumed; could not run `git status`):

- `MemPalace_Cowork_Kickoff_v1.0.md` (the kickoff doc Matt placed in the folder; not in `.gitignore`)
- `pytest-cache-files-hzcavgs3/` (not in `.gitignore`)
- `.pytest_cache/` (gitignored — won't show as untracked)

`.gitignore` confirmed to exclude: `*.egg-info/`, `dist/`, `build/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `mempal.yaml`, `.a5c/`.

---

## 3. Host environment

| Tool | Status | Notes |
|---|---|---|
| Python 3.14.3 | INSTALLED at `C:\Users\phatt\AppData\Local\Programs\Python\Python314\python.exe` | Reachable via `py -3.14`. Direct `python` invocation hangs from this Cowork session due to a broken `VIRTUAL_ENV` pointer inherited from Windows-MCP. Matt's own terminal will not have this issue. |
| pip | Bundled with Python 3.14 | Could not exercise via Windows-MCP (same hang). Will work in Matt's terminal. |
| uv 0.11.3 | INSTALLED at `C:\Users\phatt\AppData\Local\Microsoft\WinGet\Links\uv.exe` | Functional. Good fallback for venv creation. |
| Node v24.14.0 | INSTALLED at `C:\Program Files\nodejs\node.exe` | Available for `npm install -g @anthropic-ai/claude-code` if we go the Claude Code path. |
| `claude` CLI | **NOT INSTALLED** | No claude.cmd/.exe on PATH; no `~\AppData\Roaming\npm` directory. Blocks D2's plugin path. |
| coolify.interactep.app | Reachable (HTTP 200) | Cloudflare tunnel is online; the Coolify deployment path is feasible if/when Cowork supports remote MCP. |
| github.com | Reachable | Push/pull will work. |
| Disk free on C: | 83.9 GB | Plenty of headroom for ChromaDB palace, even after mining 12 GB of Claude Projects. |

Known PATH oddities (cosmetic, not blocking):

- `python` (no version) resolves to `C:\Users\phatt\AppData\Roaming\uv\python\cpython-3.13.12-windows-x86_64-none\python.exe` which **does not exist**. Matt at some point had UV install 3.13.12 and then deleted it without unregistering. Fix: either remove the stale PATH entry or run `uv python install 3.13.12` to repopulate. Using `py -3.14` sidesteps this entirely.
- `VIRTUAL_ENV` is set to `C:\Users\phatt\AppData\Roaming\Claude\Claude Extensions\ant.dir.cursortouch.windows-mcp\.venv` — a venv whose underlying interpreter is gone. This is an artefact of the Windows-MCP extension and only affects subprocesses spawned from inside Cowork; Matt's own terminal will not inherit this.

---

## 4. Pytest regression gate

**Not executed this session.** See ISSUE-1. The HARDENING_CHANGELOG.md claims "All 85 tests pass" as of the 2026-04-09 hardening pass. We have not re-verified.

To re-verify before Phase 1, run in Matt's terminal (not Cowork):

```powershell
cd "C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork"
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest tests/ -v
```

Expected result: `85 passed`. If anything other than 85 passes, treat as a blocker on Phase 1.

---

## 5. Corpus inventory (sources to mine)

| Source | Files | Size | Recommended mode | Recommended action |
|---|---|---|---|---|
| `C:\Users\phatt\Desktop\Claude Workspace\Claude Projects\` | 1,542 | 12.36 GB | `projects` | Mine subdirectory by subdirectory; **skip Event Guy University** (11.5 GB, almost entirely media) |
| `C:\Users\phatt\Documents\GitHub\atlas\` | 928 | 49.2 MB | `projects` | Mine wholesale; respect `.gitignore`; skip `node_modules`/`.next`/`migrations_backup_*` if any |
| `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\` | 128 | 2.3 MB | `projects` | Mine after Phase 1 as a dogfood test; small, fast |
| Claude.ai chat exports | — | — | `convos` | **Not found** in Downloads/Desktop/Documents. If Matt has them elsewhere, point us at the path; otherwise request a fresh export from Claude.ai. |
| Slack exports | — | — | `convos` | **Not found** in standard locations. Skip unless Matt provides one. |

Top "Claude Projects" subdirectories by file count and size (text-rich targets are starred):

```
*Events App                                 6,422 files    145.9 MB
*Executive App                              3,765 files    325.2 MB
 Event Guy University                          583 files 11,777.8 MB   ← MEDIA, SKIP
*Atlas CRM                                     215 files    286.0 MB
*Marketing Content                              44 files    156.4 MB
*Content Management System                      48 files      1.4 MB
*Architecture Documentation                     14 files     31.5 MB
 FNB Tools                                      70 files      0.3 MB
*Atlas Framework Documents                       6 files      2.9 MB
*Governance Documents                            7 files      0.9 MB
 Park Location Database Project                  3 files      6.0 MB
 Admin App                                      27 files      1.2 MB
 Claude Pulse                                   23 files      0.1 MB
```

**Phase 3 mining sequence (proposed):**

1. Architecture Documentation, Atlas Framework Documents, Governance Documents — small + decision-dense — first pass.
2. Atlas CRM, Content Management System, Marketing Content — moderate size, medium density.
3. Events App, Executive App — large but high-signal codebases — last in the sequence so we can tune mining flags first.
4. Skip Event Guy University unless Matt explicitly wants the (presumably) text portions mined.

---

## 6. Recommended consumption pattern (D2 default)

Three plausible deployment shapes:

1. **Cowork stdio MCP add (PRIMARY)** — register the mempalace MCP server as a stdio MCP in Cowork's MCP config, pointing at `py -3.14 -m mempalace.mcp_server`. Gives this Cowork session direct access to the 19 mempalace tools without a network leg. Works today.
2. **Claude Code plugin** — `claude plugin marketplace add milla-jovovich/mempalace` then `claude plugin install --scope user mempalace`. Requires installing Claude Code first (`npm install -g @anthropic-ai/claude-code`). Recommended for terminal-driven sessions.
3. **Coolify-hosted HTTP MCP** — DEFER. Cowork doesn't reliably support remote MCP yet, and the security boundary needs more thought (the palace would be exposed over HTTP).

**Recommended:** start with (1) for fast feedback in Cowork, then add (2) once Claude Code is installed. Skip (3) for now per the kickoff guidance.

---

## 7. Decisions needed from Matt (D1–D9)

For each decision, I've listed the recommended default. Matt can confirm with a short reply (e.g. "D1 default, D3 separate wings, D9 use my draft below…").

| # | Decision | Recommended default | Why |
|---|---|---|---|
| **D1** | Palace location | **`~/.mempalace/palace`** (resolves to `C:\Users\phatt\.mempalace\palace` on Windows) | Hardening fix #14 forces `MEMPAL_DIR` under `$HOME` — anywhere else fails validation. Default keeps state out of the fork tree, makes backup independent. |
| **D2** | Consumption pattern | **stdio MCP-add in Cowork now + install Claude Code in Phase 5; defer Coolify** | Fastest path to a usable memory in this session. Plugin install layered on top once Code is present. |
| **D3** | Wings | **Separate wings: `wing_iep`, `wing_atlas`, `wing_mega` (and optionally `wing_personal`)** | Wings are projects; halls are topics. The fork's IEP halls (events/venues/vendors/…) all apply *within* each wing. Separate wings give +12% retrieval accuracy. |
| **D4** | Claude.ai chat exports | **Skip — none found** | If Matt has them under a non-standard path, point us at it; otherwise request a fresh export from Claude.ai if conversation history matters. |
| **D5** | Slack exports | **Skip unless Matt provides one** | Not present on disk. Pulling Slack history is a separate, non-trivial setup step. |
| **D6** | Push hardening commits to origin | **Already done — only the version tag is missing.** Recommend creating + pushing tag `v3.0.14-iep-hardened` in Phase 8. | `local main` = `origin/main` = `252e440…`. Hardening is public. No tag yet. |
| **D7** | Auto-save hooks scope | **Project-scoped only** — start with mempalace-fork itself and Atlas via `.claude/settings.local.json`; do NOT install a user-global Stop/PreCompact hook | User-global firing every session blows up the palace with noise. Project-scoped opt-in keeps the palace focused on real work. |
| **D8** | Upstream sync cadence | **Monthly + on major upstream version bumps** | Catches the upstream fixes the README's April 7 note flagged (#100 ChromaDB pin, #110 shell injection, #74 macOS segfault) without per-PR merge churn. |
| **D9** | Identity layer (~50 tokens) | **Draft below** — Matt to edit | Drives every wake-up; should be terse and Matt-shaped. |

**D9 draft (`~/.mempalace/identity.txt`):**

```
I am Matt's AI memory, organized as a palace. Wings are projects:
IEP, Atlas, MEGA, personal. Halls cover events, venues, vendors,
timelines, budgets, team, clients, productions, equipment, creative,
technical. Save verbatim — no summaries. Search the palace before
answering anything about Matt's work.
```

(~52 tokens by rough estimate; Matt can replace.)

---

## 8. Issues and open items

- **ISSUE-1: Pytest gate not re-run.** Python execution hangs under Windows-MCP because `VIRTUAL_ENV` is set to a venv whose interpreter no longer exists. Workaround: Matt runs `py -3.14 -m pytest tests/ -v` in his own terminal, or we resolve in Phase 1 by creating a fresh `.venv` and only running tests inside it. Phase 1 cannot proceed until 85/85 is confirmed.
- **ISSUE-2: Claude CLI not installed.** Adds an `npm install -g @anthropic-ai/claude-code` step before Phase 5 if D2 includes the Code plugin path.
- **ISSUE-3: Stale `python` PATH entry.** `python` on PATH points at a non-existent UV-managed Python 3.13.12. Cosmetic; not blocking. Optional cleanup: remove the bad PATH entry or run `uv python install 3.13.12`.
- **ISSUE-4: Untracked items in working tree.** `MemPalace_Cowork_Kickoff_v1.0.md` and `pytest-cache-files-hzcavgs3/` are not in `.gitignore`. Recommend either committing the kickoff doc (under a `docs/` subfolder, with a clear name) or adding both to `.gitignore` before any future commit.

---

## 9. Proposed Phase 1+ plan (refines the kickoff)

| Phase | Goal | Gate |
|---|---|---|
| 1 | Create `.venv` with `py -3.14 -m venv .venv`; `pip install -e ".[dev]"`; run `pytest tests/ -v` | **85/85 must pass** |
| 2 | `mempalace init <Atlas dir>` to detect rooms/entities; write `~/.mempalace/config.json`; write `~/.mempalace/identity.txt` per D9 | Config sanity check |
| 3 | Mine selected `Claude Projects/` subdirectories in `projects` mode (skip Event Guy University); verify with sample searches | Search returns relevant verbatim drawers |
| 4 | Mine atlas codebase in `projects` mode (respect .gitignore); verify cross-wing tunnel between IEP and Atlas wings | `mempalace search` finds same room across wings |
| 5 | Install Claude Code (npm global); install mempalace plugin; run end-to-end query through Code | Real query answers from palace |
| 6 | Wire Stop + PreCompact hooks into `mempalace-fork/.claude/settings.local.json` and `atlas/.claude/settings.local.json`; set `MEMPAL_DIR` per project | Hook log shows trigger on save |
| 7 | (DEFERRED) Coolify HTTP MCP — only if Cowork's remote MCP support solidifies | n/a this round |
| 8 | Create + push tag `v3.0.14-iep-hardened` to origin (commits already pushed) via `cowork-git-push` | Tag visible on github.com |

---

## 10. STOP — awaiting Matt's approval

I have not run `pip install`, `pytest`, or any state-changing command. The fork is exactly as I found it. I'm holding here for:

1. Matt's responses on D1–D9.
2. Confirmation that pytest 85/85 still passes (Matt runs it once in his own terminal, or we run it together in Phase 1).
3. Approval to begin Phase 1.
