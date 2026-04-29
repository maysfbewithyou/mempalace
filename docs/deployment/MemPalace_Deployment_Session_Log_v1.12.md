# MemPalace Deployment — Session Log v1.12

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.11.

---

## v1.0–v1.11 — Summary

- v1.0–v1.9: Phase 0 audit + Discovery Report + nine decisions D1–D9 locked.
- v1.10: Phase 2 Architecture v0.2 locked (A1–A8); Claude.ai export inspected.
- v1.11: Phase 2a code shipped (http_server.py, __main__.py update, pyproject bump, 16 tests). Self-review fixes applied (eager app construction; lifespan-bypass test fixture rewrite). Pytest 85+16 confirmed by Matt.

---

## v1.12 — Phase 2b artifacts shipped (2026-04-27)

Phase 2a → 2b transition: Matt confirmed pytest green, said "go" again. Phase 2b ships the container surface — Dockerfile, ignore-rules, Coolify compose definition, two smoke-test scripts, and a step-by-step runbook for local verification.

### Files created in this phase

| File | Status | Size | Purpose |
|---|---|---|---|
| `Dockerfile` | NEW | ~3.2 KB | Multi-stage: `python:3.12-slim` builder → slim runtime. Non-root user mempalace:1000. HOME=/data. Single uvicorn worker. HEALTHCHECK via curl. |
| `.dockerignore` | NEW | ~1.4 KB | Excludes `.git`, tests, benchmarks, session logs, hooks, plugin manifests, examples — anything that doesn't need to ship in a runtime image. |
| `docker-compose.coolify.yml` | NEW | ~3.9 KB | Coolify-shaped service: build context, named volume `mempalace_data:/data`, env vars (bearer token from Coolify secret store), healthcheck, restart policy, 1G/1.0 limits, log rotation. |
| `smoke_test.sh` | NEW | ~4.4 KB | Bash + curl. Four automated checks: /health, /mcp 401 unauth, /mcp initialize round-trip, /mcp tools/list returns ≥8 mempalace_* tools. Plus printed instructions for the manual Cowork-side check. |
| `smoke_test.ps1` | NEW | ~4.4 KB | PowerShell equivalent for Matt's native Windows environment. |
| `MemPalace_Phase_2b_Local_Container_Runbook_v0.1.md` | NEW | ~5.5 KB | Step-by-step runbook for Matt: generate token, build image, run container, smoke-test, hand back. |

### Architecture compliance check (vs Phase 2 Architecture v0.2)

| Decision | Implementation in 2b artifacts |
|---|---|
| A2 — `python:3.12-slim` | ✅ ARG PYTHON_VERSION=3.12-slim in Dockerfile, used in both build and runtime stages. |
| A4 — Single uvicorn worker | ✅ CMD hardcodes `--workers 1`. Comment in Dockerfile + compose explains why. |
| A5 — Bearer token storage | ✅ Token comes from `MEMPALACE_BEARER_TOKEN` env var (Coolify secret store in production; ephemeral env var locally). Runbook step 1 generates a token; step 5 hands off to A5's `~/.mempalace_client/token` storage in 2c. |
| A6 — `/health` unauth | ✅ HEALTHCHECK + smoke-test step 1 both hit `/health` without auth and expect 200. |
| A7 — First-boot bootstrap | ✅ Lifespan auto-runs bootstrap on container start. Volume can be empty; bootstrap creates config.json + identity.txt before subprocess spawns. Verified via runbook step 3 logs. |
| A8 — Resource limits | ✅ `deploy.resources.limits: memory: 1G, cpus: "1.0"` in compose. Note: docker-compose v3 only enforces these in Swarm mode; standalone `docker compose` ignores them but Coolify's compose driver respects them. |

### Side note — voice-mode test signal

A `mcp__9b495fde-09d2-4c1e-9dc6-81ba65d829cb__get_voice_test_token` deferred tool surfaced in this Cowork session's tool list during 2b, with no commentary from Matt (he just said "go" to proceed with 2b). Hypothesis: this is Matt's external voice-mode test thread (ISSUE-5) bringing up an MCP that this session can call. Not engaged in 2b; logged here for ISSUE-5 / Phase 10 follow-up. To revisit AFTER Phase 2c smoke test confirms hosted MemPalace is live.

### Phase 2b verification gate

The Phase 2b → 2c gate is Matt's local container smoke test:

1. `docker build -t mempalace-iep:0.1 .` — image builds cleanly (~2-5 min first time).
2. `docker run … mempalace-iep:0.1` — container starts, bootstrap log lines appear, uvicorn binds 8000.
3. `.\smoke_test.ps1 -BaseUrl http://localhost:8000 -Token $env:MEMPALACE_BEARER_TOKEN` — all 4 automated checks PASS.

If any check fails, that's a 2b blocker — fix before 2c.

### What 2c will do once 2b clears

- Push the fork to GitHub origin (we already have most of main pushed; the Phase 2a/2b new files need to land too).
- In Coolify UI: create a new "Application" pointing at `maysfbewithyou/mempalace` repo, branch `main`, build pack `Docker Compose`, compose file `docker-compose.coolify.yml`.
- Set the `MEMPALACE_BEARER_TOKEN` secret in Coolify before first deploy.
- Trigger deploy. Watch Coolify build logs. When healthcheck passes, container is live on Coolify's internal network.
- 2d follows immediately: add Cloudflare tunnel ingress for `mempalace.tstly.dev` → internal Coolify hostname. Verify `https://mempalace.tstly.dev/health` returns 200.
- 2e: re-run `smoke_test.ps1` against `https://mempalace.tstly.dev` instead of localhost. All 4 should still pass.

### Issues carried forward

- ISSUE-2 (open): `claude` CLI not installed (Phase 7).
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-5 (parked, Phase 10): voice-mode tool support — Matt testing externally; voice test token deferred-tool now surfaced (see "Side note" above).
- ISSUE-6 (parked, Phase 6): Claude.ai export mining queued.
- ISSUE-7 (parked, Phase 11): Slack mining design.
- ISSUE-8 (Phase 8): Verify Stop hook merge behavior.

### Versioning policy

Every artifact carries a version stamp. Code modules carry their own version headers. Each prior session-log version preserved as a rollback anchor.
