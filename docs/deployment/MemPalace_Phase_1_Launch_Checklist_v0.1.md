# MemPalace — Phase 1 Launch Checklist (v0.1)

Date: 2026-04-27
Decisions all locked in `MemPalace_Deployment_Session_Log_v1.9.md`.

---

## What unblocks Phase 1

There is exactly **one blocker** between us and Phase 1 starting: **pytest 85/85 must pass on your laptop.** I couldn't run it from Cowork because Windows-MCP inherits a broken `VIRTUAL_ENV` pointer that hangs every Python invocation. The fix is for you to run it once in your own terminal.

### The 90-second pytest check

Open PowerShell (not inside Cowork — your own Terminal or Windows Terminal):

```powershell
cd "C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork"
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest tests/ -v
```

What I'm watching for:

- The last line of pytest output should read `===== 85 passed in NN.NNs =====`. Anything else is a regression — please paste me the failing test names and we triage before Phase 2.
- The hardening changelog claims 85/85 as of the 2026-04-09 work. We have not re-run since.
- This venv stays at `mempalace-fork\.venv\`. It's gitignored under upstream's `.gitignore` rules already, so no cleanup needed.

When you've got 85/85, post back something like *"pytest 85/85, go"* and I'll start Phase 2.

---

## In parallel — the export request (D4 follow-up)

While pytest runs, please also kick off the Claude.ai data export:

1. Open https://claude.ai → click your avatar → **Settings**
2. **Privacy** → **Export data** → confirm
3. You'll get an email when the ZIP is ready (typically several hours). Drop the ZIP into `C:\Users\phatt\Downloads\` when it lands and I'll handle the rest in Phase 6.

---

## What happens after Phase 1 (preview)

Once pytest passes, the deployment moves through these phases without further decisions from you (other than the obvious approve-before-push moments):

| Phase | What I do | When |
|---|---|---|
| **2** | Stand up MemPalace HTTP wrapper + bearer auth + Cloudflare tunnel on Coolify at `mempalace.tstly.dev`. New code, lives in the fork. | Immediately after pytest passes |
| **3** | Initialize the hosted palace; write your D9 identity.txt; create the four wings. | After Phase 2 health-check passes |
| **4** | Mine selected `Claude Projects/` subdirs into the hosted palace, routing per D3. | After Phase 3 |
| **5** | Mine the `atlas/` codebase into `wing_atlas`; verify cross-wing tunnels. | After Phase 4 |
| **6** | When your Claude.ai export ZIP arrives, mine it via `--mode convos --extract general`. | When the export downloads |
| **7** | Install Claude Code on your laptop; wire it up to the hosted MCP via bearer header. | After Phase 6 (or in parallel with 6) |
| **8** | Wire hooks (D7 hybrid scope); create the weekly hook-review and monthly upstream-diff scheduled tasks (D7 + D8). | After Phase 7 |
| **9** | v1.0 closeout: move all our deployment docs into `docs/deployment/`, commit, tag `v3.0.14-iep-hardened`, push, delete stale `security/hardening-v3` branch. | Final step of v1.0 |
| **Post-v1.0 / Phase 10** | OAuth wrapper for claude.ai web/mobile/voice. Driven by what your other thread tells us about voice-mode tool support. | When you're back from the voice test |
| **Post-v1.0 / Phase 11** | Slack mining design + execution per D5. | When you're ready to scope it |

Each phase produces a versioned artifact in this folder (Session Log v2.0, v2.1, … as we move through them; Architecture doc v0.1 in Phase 2; etc.) so any phase can be rolled back to the artifact captured before it.

---

## Your immediate todo list

1. Run the 90-second pytest check and report back.
2. Trigger the Claude.ai data export (don't wait for it — fire and forget).
3. Confirm you'd like me to start Phase 2 the moment pytest is green, or give me a hold signal if you want to pause for any reason.

---

## My immediate todo list (parallel work I can start before Phase 2 kicks off)

While you run pytest, I can do these without touching your machine state:

- Draft the Phase 2 Architecture doc (`MemPalace_Phase_2_Architecture_v0.1.md`) covering the HTTP wrapper design, the Dockerfile, the Coolify service config, and the Cloudflare tunnel routing — so you can review the design before I push code.
- Spec the bearer-token generation + storage flow (where the secret lives, how it's rotated, how each client gets it).
- Pick the HTTP MCP transport library (FastMCP vs hand-rolled Starlette vs the official `mcp.server.streamable_http` module) and justify the choice.

Want me to start the Phase 2 architecture draft while pytest runs? It's pure design work — no commits, no installs, no changes on your end. You'd review v0.1 and we'd lock it before any code goes near Coolify.
