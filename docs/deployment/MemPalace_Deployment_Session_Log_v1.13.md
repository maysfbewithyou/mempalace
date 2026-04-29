# MemPalace Deployment — Session Log v1.13

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Status: **Phase 2 COMPLETE — hosted MemPalace live at https://claude-brain.tstly.dev**

> Earlier session-log snapshots: v1.0–v1.12.

---

## v1.13 — Phase 2 deployment milestone (2026-04-27)

### What's live

- URL: `https://claude-brain.tstly.dev`
- Container: `mempalace-http-xbpmh19e5pxv7dxkcweo86oq-*` on Coolify host `atlas-dev-server`
- Bearer-auth: enforced on `/mcp`; lightweight liveness on `/health`; deep readiness on `/ready`
- Tunnel: `claude-brain.tstly.dev` → `http://localhost:5042` via existing `atlas-dev` Cloudflare tunnel
- All 19 upstream `mempalace_*` MCP tools surfaced and reachable through the tunnel
- Single source of truth for D1 (Path A) — palace state in Docker volume `mempalace_data:/data` on the Coolify host

### Smoke test result (final)

```
ALL AUTOMATED CHECKS PASSED
1/4 PASS  health endpoint returns 200 ok
2/4 PASS  unauthenticated request rejected with 401
3/4 PASS  initialize round-trip succeeded
4/4 PASS  tools/list returned 19 mempalace_* tools
```

### Commits shipped to origin during Phase 2

1. `48d3cd1` — feat: hardening pass + IEP personalization + HTTP wrapper (Phase 2a; first attempt)
2. `1bed802` — fix: use expose instead of ports binding to avoid host port 8000 conflict
3. `5e7460c` — fix: run container as root to avoid Docker volume ownership mismatch
4. `52fec6a` — fix: bind host port 5042 for cloudflared tunnel routing
5. `3e8cdfe` — fix: lightweight /health for Docker; deep check moved to /ready; longer start_period for ChromaDB ONNX init
6. `b63db2b` — fix: env var array syntax so Coolify runtime injection populates MEMPALACE_BEARER_TOKEN

Six commits total. The first carried the entire hardening + IEP personalization + wrapper code (~2,800 line delta). The remaining five each addressed a specific deployment friction point.

### Iteration cycles encountered (lessons learned)

| # | Issue | Root cause | Fix |
|---|---|---|---|
| 1 | Container failed to start | Host port 8000 already allocated | Switched compose `ports` to `expose` initially, later to `5042:8000` once we understood Matt's tunnel-to-host-port pattern |
| 2 | 502 from tunnel | Misunderstood tunnel pattern — Matt routes `*.tstly.dev` → unique `localhost:<port>` per app, not via shared traefik proxy | Bound a unique host port (5042) and added Cloudflare tunnel public hostname rule mapping `claude-brain.tstly.dev` → `localhost:5042` |
| 3 | Container restart loop, no logs | Docker mounted fresh volume to `/data` overrode image-set ownership; non-root user couldn't write | Removed `USER mempalace` directive — runs as root in v1 (acceptable for single-user personal deployment) |
| 4 | Container restart loop after volume fix | `/health` round-tripped to StdioProxy with 5s timeout; ChromaDB ONNX model download on first boot exceeds that → Docker thought container was unhealthy and restarted before init completed | Made `/health` a lightweight liveness check (returns ok if wrapper alive); added separate `/ready` endpoint for the deep proxy check; bumped Docker `start_period` to 120s |
| 5 | RuntimeError "MEMPALACE_BEARER_TOKEN env var is required" inside container | Two compounding bugs: (a) compose's `${MEMPALACE_BEARER_TOKEN}` substitution resolved to empty if Coolify didn't export it to the compose shell; (b) Coolify UI's first Save didn't persist the value (saved key only) | Switched compose to array syntax (`- MEMPALACE_BEARER_TOKEN`) so env vars pass through; re-pasted the value in Coolify UI and clicked Update; verified via `docker inspect` that the token is now populated |

### Architecture decisions revisited

All A1–A8 from `MemPalace_Phase_2_Architecture_v0.2.md` held. Two implementation refinements emerged during deploy that are worth recording for future-Matt:

- **A4 (single uvicorn worker)** — confirmed correct. Adding worker count would have caused multiple StdioProxy subprocesses against one ChromaDB.
- **A6 (`/health` unauth)** — refined. Originally `/health` was the deep readiness check; now it's lightweight liveness. The deep check moved to `/ready`.

### Token security

The bearer token was pasted into a chat screenshot earlier in this deploy session for diagnosis. Recommend rotating after the deployment is fully validated and stable. Rotation procedure (~3 min):

1. PowerShell on laptop: regen + save + clipboard (single-line command from earlier — stored in `C:\Users\phatt\.mempalace_client\token`)
2. Coolify UI → Environment Variables → MEMPALACE_BEARER_TOKEN → paste new value → Update
3. Coolify Redeploy
4. Verify `/health` 200 + smoke test passes against new token

Rotation is an addressable follow-up (not blocking Phase 3+).

### Next: Phase 3 (init hosted palace + identity.txt verification)

Bootstrap already ran on container startup — `bootstrap_if_needed()` in `http_server.py` writes `config.json` + `identity.txt` on first boot if absent. Phase 3 is now mostly verification:

1. SSH into container or use Coolify Terminal to confirm `/data/.mempalace/config.json` exists with the four-wing layout (D3) and `/data/.mempalace/identity.txt` matches D9 Draft C content.
2. Run `mempalace status` over the MCP to confirm wing structure.
3. Set the bearer-MCP entry in Cowork's MCP config so we can talk to the palace from this Cowork session — the manual step the smoke test #5 referenced.

### Issues carried forward

- ISSUE-2 (open, Phase 7): `claude` CLI not installed.
- ISSUE-3 (cosmetic): stale `python` PATH entry on laptop.
- ISSUE-5 (parked, Phase 10): voice-mode tool support — Matt testing externally; the `get_voice_test_token` deferred tool surfaced earlier confirms voice MCP infra works on Matt's other thread.
- ISSUE-6 (parked, Phase 6): Claude.ai export ZIP awaiting mining.
- ISSUE-7 (parked, Phase 11): Slack mining design.
- ISSUE-8 (Phase 8): Verify Stop hook merge behavior.
- ISSUE-9 (resolved): No Docker on laptop — workaround was to push direct to Coolify (Coolify's host has Docker).
- ISSUE-10 (resolved during Phase 2c): git-via-Windows-MCP hang. Matt's other-session fix (PATH-priority `git.cmd` shim with `<NUL` redirect + persistent `GIT_TERMINAL_PROMPT=0` / `GCM_INTERACTIVE=Never`) installed mid-deploy. Last few commits driven directly through Windows-MCP PowerShell.
- ISSUE-11 (NEW, low-priority): bearer token visible in earlier screenshots → rotate before treating as long-lived. Tracked.

### Versioning policy

Every artifact carries a version stamp. Decision and design locks bump session-log minor version. Each prior session-log version preserved as a rollback anchor.
