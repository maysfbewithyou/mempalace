# MemPalace — Phase 2c Coolify Deploy Runbook (v0.1)

Date: 2026-04-27
Status: READY for Matt to execute. Phase 2b skipped (no local Docker).

> **What this is:** push the Phase 2a+2b code to GitHub origin, then set up a Coolify Application that pulls from origin, builds the image on the Coolify host, runs it with bearer auth, and exposes it on Coolify's internal network for Phase 2d's tunnel routing.

---

## Part A — Push code to GitHub (PowerShell)

Reuses the same PowerShell window from Phase 2b step 1. If you closed it, re-run step 1 of the 2b runbook to regenerate the bearer token first — you'll need it again in Part B.

### A.1 — Confirm what's about to be committed

```powershell
cd "C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork"
git status
```

You should see roughly this (file order may vary; `MemPalace_*.md` and `pytest-cache-files-*` will appear as untracked but we DON'T commit them — those land in Phase 9):

```
Untracked files:
        Dockerfile
        .dockerignore
        docker-compose.coolify.yml
        smoke_test.ps1
        smoke_test.sh
        mempalace/http_server.py
        tests/test_http_server.py

Modified:
        mempalace/__main__.py
        pyproject.toml
        (lots of MemPalace_*.md files — DO NOT add these)
```

### A.2 — Stage only the code files

```powershell
git add `
    Dockerfile `
    .dockerignore `
    docker-compose.coolify.yml `
    smoke_test.ps1 `
    smoke_test.sh `
    pyproject.toml `
    mempalace/http_server.py `
    mempalace/__main__.py `
    tests/test_http_server.py
git status
```

You should now see only those 9 files staged (under "Changes to be committed"). The `MemPalace_*.md` files should still be in "Untracked" — that's correct, they don't ship in this commit.

### A.3 — Commit and push

```powershell
git commit -m "feat: HTTP wrapper for hosted MemPalace deployment (Phase 2a+2b)

- Add mempalace/http_server.py: Starlette + uvicorn wrapper around the
  upstream stdio MCP server. Bearer-token auth, StdioProxy subprocess
  manager with auto-restart, /mcp + /health endpoints, first-boot
  bootstrap of config.json + identity.txt.
- Add tests/test_http_server.py: 16 tests covering auth, body validation,
  bootstrap, env-var hardening, and real-subprocess integration.
- Add Dockerfile (multi-stage, python:3.12-slim, non-root, /data home).
- Add .dockerignore, docker-compose.coolify.yml, smoke_test.{ps1,sh}.
- Update __main__.py to add 'serve-http' subcommand intercept (keeps
  upstream cli.py untouched for clean monthly upstream sync).
- Bump version to 3.0.14+iep.1 (PEP 440 local version)."
git push origin main
```

**Paste me the output of `git push`.** Expected: a few lines about object counting + `Writing objects: 100%` + `To https://github.com/maysfbewithyou/mempalace.git` + `<short hash>..<short hash> main -> main`. If push prompts for credentials, use your GitHub PAT.

---

## Part B — Coolify Application setup (Coolify UI)

I don't know exactly how your Coolify UI is laid out, so this is a generic walk-through. **Where the UI differs from what's described, screenshot or describe what you see and we'll adjust.**

### B.1 — Sign in and pick / create the project

1. Open https://coolify.interactep.app in your browser.
2. Sign in.
3. Look for a "Projects" section in the sidebar.
4. If you have an existing project that fits ("Personal", "MEGA", "Internal Tools" — your call), use it. Otherwise click **New Project** → name it `mempalace` → save.

Tell me which project you put it under so I can reference it later.

### B.2 — Add the Application resource

Inside the chosen project:

1. Click **Add New Resource** (or **+ New** depending on Coolify version).
2. Pick **Application** → **Public Repository** OR **Private Repository (via GitHub App)** depending on how your fork is configured. Since `maysfbewithyou/mempalace` may be private, you'll likely want the GitHub App route.
3. If GitHub isn't connected yet to Coolify: Coolify will prompt you to install the Coolify GitHub App; follow the prompts and grant access to `maysfbewithyou/mempalace`.

### B.3 — Configure the Application

Fill in:

| Field | Value |
|---|---|
| Repository | `https://github.com/maysfbewithyou/mempalace` |
| Branch | `main` |
| Build pack | **Docker Compose** |
| Compose file | `docker-compose.coolify.yml` |
| Base directory | `/` (the repo root) |
| Application name | `mempalace-http` (matches the service name in the compose file) |

Save.

### B.4 — Set environment variables

Find the **Environment Variables** (or **Secrets**) tab on the Application's page.

Add a single secret:

| Key | Value |
|---|---|
| `MEMPALACE_BEARER_TOKEN` | the 44-char token currently in your PowerShell `$env:MEMPALACE_BEARER_TOKEN` |

In your PowerShell, run this to get the token text to paste:

```powershell
$env:MEMPALACE_BEARER_TOKEN
```

Copy the output, paste into Coolify, mark it as a **secret** (so it's masked in the UI). **Save.**

> **Important:** the token must be marked secret AND must be available at runtime to the container. Coolify's UI may use checkboxes labeled "Build Time", "Runtime", or "Both" — runtime is what we need (build doesn't reference it).

### B.5 — Trigger first deploy

Click the **Deploy** button.

Coolify will:

1. Clone `maysfbewithyou/mempalace` at branch `main`.
2. Run `docker compose -f docker-compose.coolify.yml build` — first build is 2–5 minutes.
3. Start the container with `MEMPALACE_BEARER_TOKEN` injected.
4. Run the healthcheck (curl /health) every 30s. Container is "healthy" once it returns 200.

Watch the **Deploy Logs** in the Coolify UI. You should see:

- The build stages (downloading python:3.12-slim, installing wheels, etc.)
- Then container startup logs (similar to what we'd have seen locally):
  ```
  INFO startup: palace_path=/data/.mempalace/palace
  INFO bootstrap: config initialized at /data/.mempalace/config.json
  INFO bootstrap: identity.txt written at /data/.mempalace/identity.txt
  INFO stdio_proxy: spawning python -m mempalace.mcp_server --palace ...
  INFO stdio_proxy: subprocess pid=N started
  INFO startup complete
  INFO Application startup complete.
  INFO Uvicorn running on http://0.0.0.0:8000
  ```

**Paste me the Deploy Log output once you see either "healthy" status or any error.**

### B.6 — Verify container health

Once deployed:

1. Coolify Application page should show status **Running** + healthcheck **Healthy**.
2. Coolify will also show an **internal URL** (something like `http://mempalace-http:8000` or a Coolify-assigned hostname). Note this.
3. There may also be a Coolify-assigned **public URL** (e.g., `https://mempalace-http.coolify.interactep.app` or similar) if your Coolify auto-creates Cloudflare-fronted URLs. If you see one, capture it — that's a quick way to test before we wire up `mempalace.tstly.dev`.

If a Coolify-assigned public URL is available, you can run the smoke test against it now:

```powershell
.\smoke_test.ps1 -BaseUrl https://<coolify-assigned-url> -Token $env:MEMPALACE_BEARER_TOKEN
```

If smoke passes there, we're 95% certain the wrapper is working. The remaining 5% is the `mempalace.tstly.dev` hostname routing in 2d.

If no public URL or you want to skip that and go straight to the proper domain — fine, jump to 2d.

---

## What 2c is done

Phase 2c is complete when:

1. Code is on `origin/main` (Part A.3 push succeeded).
2. Coolify Application is **Running + Healthy**.
3. Either: smoke_test.ps1 passes against a Coolify-assigned URL, OR Coolify reports the container as healthy and we accept that as 2c-done and move to 2d.

---

## Hand back to me

After Part A: paste the `git push` output.
After Part B: paste the Deploy Log + final container status, and either the Coolify-assigned URL or "no auto URL, skip to 2d."

Once 2c is green, I write the 2d runbook (Cloudflare tunnel ingress for `mempalace.tstly.dev`).
