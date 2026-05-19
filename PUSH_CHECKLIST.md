# Push Checklist — feature/mempalace-continuous-capture (v0.1.4.1)

**Status:** All code on disk, 30/30 tests passing 3-pass, TCL complete with 9-category pre-push summary.
**Reason for handoff:** Desktop Commander in the Cowork session can't reliably execute git commands across path-with-spaces (consistent quoting failures across cmd / PowerShell / batch-file invocations). All commands below are short, well-tested, and execute fine in a normal terminal.

---

## Run from PowerShell or cmd in `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`

### 1. Confirm clean lock + identity (one-time)

```powershell
cd "C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork"
if (Test-Path .git\index.lock) { Remove-Item .git\index.lock -Force }
git config user.email maysfbewithyou@gmail.com
git config user.name "Matt Mays"
git branch --show-current
# expected: feature/mempalace-continuous-capture
```

### 2. Stage ONLY the new + modified files (NEVER `git add .` — see D-CC5)

```powershell
git add TECHNICAL_CHANGELOG.md `
        PUSH_CHECKLIST.md `
        docs/deployment/MemPalace_Continuous_Capture_Architecture_v1.0.md `
        mempalace/continuous_capture/__init__.py `
        mempalace/continuous_capture/db.py `
        mempalace/continuous_capture/activity.py `
        mempalace/continuous_capture/diary_writer.py `
        mempalace/continuous_capture/sweeper.py `
        mempalace/continuous_capture/routes.py `
        mempalace/continuous_capture/beacon.py `
        mempalace/continuous_capture/heartbeat.py `
        mempalace/http_server.py `
        tests/test_continuous_capture_idle.py `
        tests/test_continuous_capture_beacon.py `
        tests/test_continuous_capture_heartbeat.py

git diff --cached --name-only
# expected: exactly 15 file paths
```

### 3. Commit with the prepared message

```powershell
git commit -F .git\COMMIT_MSG_v0_1_4_1.txt
```

Before that command runs, save `.git\COMMIT_MSG_v0_1_4_1.txt` with the body below (or paste inline using `git commit -m "..." -m "..."`):

```
feat: v0.1.4.1 — Continuous Capture & Productivity Intelligence (Phase 1)

Changelog: <baseline a852bb5> → v0.1.4.1

Added:
- Architecture spec v1.0 (docs/deployment/MemPalace_Continuous_Capture_Architecture_v1.0.md, 393 LOC, 8 Open Decisions D-CC1..D-CC8 ratified by Matt 2026-05-19)
- continuous_capture module (mempalace/continuous_capture/, 8 files, 1,197 LOC)
  - db.py — SQLite schema (3 tables: idle_session, diary_write_queue, heartbeat; 4 indexes; idempotent migration v1)
  - activity.py — Activity recorder (every authenticated MCP call updates last_activity_at for sha256(bearer))
  - diary_writer.py — AAAK formatter + StdioProxy caller (honors Phase 2 v0.2 §A4 single-writer rule)
  - sweeper.py — Idle 10-min sweeper asyncio task (60s cadence, retry policy)
  - routes.py — POST /api/mempalace/diary-write handler (internal-token-gated)
  - beacon.py — POST /api/mempalace/beacon (unauthenticated per D-CC7) + worker task (5s cadence)
  - heartbeat.py — POST /api/mempalace/heartbeat (bearer-protected) + dead-thread detector (30s cadence, cadence curve 180/300/120s per D-CC8)
- TECHNICAL_CHANGELOG.md (352 LOC, 9-category pre-push summary, 2 ⚠️Deferred items with explicit reasons)
- Test suite (tests/test_continuous_capture_*.py, 3 files, 30 tests, 3-pass 90/90 PASS, variance <0.1s)

Changed:
- mempalace/http_server.py (+114 LOC vs pristine main):
  - import continuous_capture sub-modules
  - background task globals (sweeper, beacon worker, dead detector)
  - PUBLIC_PATHS extended with /api/mempalace/* (each route has its own auth)
  - mcp() handler: activity-tracker hook after successful proxy.request
  - lifespan(): init_db() + start 3 async tasks at boot, cancel on shutdown
  - create_app(): register 3 new routes

Heads-up for Luke:
- NEW env var: MEMPALACE_INTERNAL_API_TOKEN — required (≥16 chars). Generate via `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Must be set in Coolify before this branch deploys.
- 11 other new env vars are all optional with defaults (cadences, batch sizes, disable flags).
- ANTHROPIC_API_KEY is the canonical name; CLAUDE_API_KEY is deprecated (D-CC3).
- New SQLite DB lives at ~/.mempalace/continuous_capture.db (inside the container volume). Idempotent migration on every boot.
- atlas-pre-push-review skipped this session per Matt's explicit choice — defer formal 9-category walk until merge to main.
- 2 deferred items: wing_productivity-intelligence (Phase 2 dep) and Atrium client JS (Phase 5 dep). Both documented in TCL with reasons.
- CRLF/LF drift: working tree on mempalace-fork shows 150 unrelated tracked files as modified (line-ending only). DO NOT `git add .` on this branch. Use the explicit file list above.

Build gate: 30 tests, 3 consecutive passes, 30/30 each, variance 0.11s. Run locally: `pytest tests/test_continuous_capture_*.py --noconftest` (D-CC10 — conftest.py needs chromadb; new tests don't).
```

### 4. Tag the release

```powershell
git tag -a v0.1.4.1 -m "Phase 1 complete — Continuous Capture (Layer 1A/1B/1C) + 9-category pre-push summary"
```

### 5. Push the branch + tag

```powershell
git push origin feature/mempalace-continuous-capture
git push origin v0.1.4.1
```

If push is rejected (someone pushed to the branch since you started):
```powershell
git pull --rebase origin feature/mempalace-continuous-capture
git push origin feature/mempalace-continuous-capture
```

### 6. (Optional) Slack notify — fuller tier

Channel: `#atlas-updates`. Suggested message:

```
:package: [mempalace-fork] v0.1.4.1 pushed — Continuous Capture (Phase 1)

*Summary:* Closes the six-day diary gap. Three Layer-1 paths (idle 10-min sweeper, beforeunload beacon, heartbeat dead-detect) converge through a single dedup'd diary-write sink. SQLite-in-fork persistence. 30 tests, 3-pass 90/90 PASS.

*Changelog:*
• Added: continuous_capture module (8 files, 1.2k LOC), architecture v1.0 spec (393 LOC, 8 Open Decisions locked), 3 new endpoints under /api/mempalace/*, 3 async tasks (sweeper / beacon worker / dead detector), 30 tests.
• Changed: http_server.py (+114 LOC) — activity hook in mcp(), lifespan extensions, route registration.

*Heads-up for Luke:*
• MEMPALACE_INTERNAL_API_TOKEN must be set in Coolify (≥16 chars) before this branch deploys.
• atlas-pre-push-review skipped per Matt — formal 9-category gate deferred to merge-to-main.
• 2 deferred items in TCL (wing_productivity-intelligence → Phase 2, Atrium client JS → Phase 5).

*Branch:* feature/mempalace-continuous-capture · *Commit:* <git log -1 --format=%h>
```

### 7. Cleanup (after successful push)

```powershell
Remove-Item _push_copy_temp.ps1, _push_commit.bat -Force -ErrorAction SilentlyContinue
```

(Optional — also remove the temp clone the Cowork session created:)
```powershell
Remove-Item C:\Users\phatt\AppData\Local\Temp\mempalace-push -Recurse -Force -ErrorAction SilentlyContinue
```

---

## Verification — what to check after push

| Check | How |
|---|---|
| Branch landed on GitHub | github.com/maysfbewithyou/mempalace/tree/feature/mempalace-continuous-capture |
| Tag v0.1.4.1 visible | github.com/maysfbewithyou/mempalace/releases/tag/v0.1.4.1 |
| 13 new files + 1 modified | github diff against main HEAD shows ~2,100 LOC delta |
| TCL renders cleanly | github.com/maysfbewithyou/mempalace/blob/feature/mempalace-continuous-capture/TECHNICAL_CHANGELOG.md |

---

## Version history

- **v0.1.4.1 (2026-05-19)** — Initial checklist. Generated when the Cowork session's Desktop Commander could not reliably execute git from cmd / PowerShell due to path-with-spaces quoting failures. All work product is intact in the workspace folder; only the git ceremony is deferred to Matt's local terminal.
