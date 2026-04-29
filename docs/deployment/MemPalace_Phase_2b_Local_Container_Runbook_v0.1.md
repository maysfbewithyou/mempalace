# MemPalace — Phase 2b Local Container Runbook (v0.1)

Date: 2026-04-27
Status: READY for Matt to execute.

> **What this is:** the exact commands to build and locally smoke-test the MemPalace container before pushing it to Coolify. Ten minutes of focused work, all on your laptop. No code changes during this runbook — you're just verifying the artifacts I just shipped behave correctly.

---

## Prerequisites

| Prereq | Check command | If missing |
|---|---|---|
| Docker Desktop running | `docker ps` returns no error | Open Docker Desktop |
| pytest 85+16 still green | covered in Phase 2a verification | re-run `pytest tests/ -v` |

---

## Step 1 — Generate a bearer token

```powershell
cd "C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork"
$env:MEMPALACE_BEARER_TOKEN = (py -3.14 -c "import secrets; print(secrets.token_urlsafe(32))")
Write-Host "Token (44 chars): $env:MEMPALACE_BEARER_TOKEN"
```

Copy the printed token. We'll use it for the smoke test, then store it for later in `C:\Users\phatt\.mempalace_client\token` (per A5) once we're past 2b.

> **Don't paste this token in chat unredacted.** It's a password. If it ever gets shared, regenerate via the same one-liner.

---

## Step 2 — Build the image

```powershell
docker build -t mempalace-iep:0.1 .
```

What to expect:

- First build downloads `python:3.12-slim` (~50 MB) and the wheels for ChromaDB + Starlette + uvicorn (~150 MB). Takes 2–5 minutes on first run, ~30 s on subsequent rebuilds (Docker layer cache).
- Final image size: roughly 350–400 MB.
- Build succeeds → you have an image tagged `mempalace-iep:0.1`.

If build fails:

- `error: chromadb` wheel issue → likely a Python version mismatch in the slim image; let me know.
- Network error pulling wheels → retry; if persistent, configure pip mirror in the Dockerfile.

---

## Step 3 — Run the container

```powershell
docker run --rm -d `
    --name mempalace-test `
    -e MEMPALACE_BEARER_TOKEN=$env:MEMPALACE_BEARER_TOKEN `
    -p 8000:8000 `
    -v mempalace_test_data:/data `
    mempalace-iep:0.1
```

Wait ~30 seconds for first-boot bootstrap (palace init, ONNX model download for ChromaDB). Watch logs:

```powershell
docker logs -f mempalace-test
```

What you should see (in order):

```
INFO startup: palace_path=/data/.mempalace/palace
INFO bootstrap: config initialized at /data/.mempalace/config.json
INFO bootstrap: identity.txt written at /data/.mempalace/identity.txt
INFO stdio_proxy: spawning python -m mempalace.mcp_server --palace /data/.mempalace/palace
INFO stdio_proxy: subprocess pid=… started
INFO startup complete
INFO Application startup complete.
INFO Uvicorn running on http://0.0.0.0:8000
```

Hit `Ctrl+C` to stop tailing logs (container keeps running in background).

---

## Step 4 — Run the smoke test

```powershell
.\smoke_test.ps1 -BaseUrl http://localhost:8000 -Token $env:MEMPALACE_BEARER_TOKEN
```

Expected output:

```
MemPalace smoke test against http://localhost:8000

1/4  GET  http://localhost:8000/health
  PASS  health endpoint returns 200 ok

2/4  POST http://localhost:8000/mcp  (no Authorization header)
  PASS  unauthenticated request rejected with 401

3/4  POST http://localhost:8000/mcp  (initialize, with bearer)
  PASS  initialize round-trip succeeded

4/4  POST http://localhost:8000/mcp  (tools/list, with bearer)
  PASS  tools/list returned 19 mempalace_* tools (expected >=8)

5/4  Manual: register the bearer-MCP in Cowork pointed at http://localhost:8000/mcp
     and run a mempalace_status query.

Summary
  passed: 4
  failed: 0

ALL AUTOMATED CHECKS PASSED
```

If anything fails:

- **Check 1 fail (no /health):** container probably didn't start — `docker logs mempalace-test` and paste me the error.
- **Check 2 fail (got something other than 401):** middleware wiring issue — paste me the response.
- **Check 3 fail (initialize didn't round-trip):** either subprocess failed to spawn OR JSON-RPC contract drifted; logs again.
- **Check 4 fail (tool count too low):** subprocess proxy is up but the upstream `mempalace.mcp_server` isn't listing tools correctly. Paste me the response body.

---

## Step 5 — Stop the container, keep the image

```powershell
docker stop mempalace-test
```

The image stays on disk (we'll push it to Coolify in 2c). The volume `mempalace_test_data` also stays — useful if you want to inspect the bootstrapped palace state. Delete it later via:

```powershell
docker volume rm mempalace_test_data
```

---

## Hand back to me

When all 4 automated checks pass, just say "go" and I'll start Phase 2c — pushing the image / repo to Coolify and getting it running on the host. If anything fails, paste me the failing output and we triage before 2c.

---

## What ships in 2b (files added to the repo this phase)

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage build (builder → slim runtime), non-root user, /data home. |
| `.dockerignore` | Keeps the build context lean — excludes `.git`, tests, benchmarks, deployment docs. |
| `docker-compose.coolify.yml` | Coolify service definition, volume mount, healthcheck, resource limits. |
| `smoke_test.ps1` | PowerShell smoke test (your platform). |
| `smoke_test.sh` | Bash smoke test (also runs in WSL / Git Bash / future Linux clients). |
| `MemPalace_Phase_2b_Local_Container_Runbook_v0.1.md` | This document. |
