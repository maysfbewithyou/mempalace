# MemPalace — Phase 2 Architecture (v0.2 — locked)

Date: 2026-04-27
Status: **LOCKED.** All design decisions A1–A8 ratified. v0.1 is the rollback anchor.

> v0.2 supersedes v0.1. The body of the architecture is unchanged from v0.1; this revision adds the lock confirmation + a plain-English explanation of each design call so future-Matt (and any other agent picking this up) can sanity-check what's committed without re-deriving the engineering reasoning.

---

## Locked decisions (A1–A8)

### A1 — Tunnel domain: `mempalace.tstly.dev` ✅ LOCKED

**What was decided:** the public hostname for the hosted MemPalace MCP server is `mempalace.tstly.dev`.

**Plain English:** This is the URL clients (Cowork, Claude Code, eventually Claude.ai) will hit. `tstly.dev` is your domain (confirmed). The `mempalace.` subdomain is what we're adding. We will add a routing rule to your existing Cloudflare tunnel that says "any HTTPS request to mempalace.tstly.dev → forward to the MemPalace container running on Coolify."

**What this depends on:**
- The existing Coolify tunnel must have permission to add new hostname routes (it does, as far as I can tell from the kickoff context).
- A DNS record for `mempalace.tstly.dev` pointing at Cloudflare. If Cloudflare manages your DNS for tstly.dev (which is the usual setup), the tunnel command can create the DNS record automatically.

**Phase 2d step:** I'll add the ingress rule and verify `https://mempalace.tstly.dev/health` responds.

---

### A2 — Container Python version: `python:3.12-slim` ✅ LOCKED

**Plain English:** Inside the container, we'll run Python 3.12 (a stable, well-tested release) on the slim Debian variant (~50 MB base image). Your laptop has Python 3.14, but the container is its own world — we pin to 3.12 because ChromaDB (the database MemPalace uses) has the most mileage on Python 3.10–3.12.

**Why not 3.14 to match your laptop:** ChromaDB 0.5.x (which the hardening work pinned us to) hasn't been heavily tested on 3.14 yet. Stability over novelty here.

---

### A3 — HTTP wrapper library: Starlette + uvicorn ✅ LOCKED

**Plain English:** Two small, well-known Python libraries. Starlette = web framework (handles routing, middleware, request/response). Uvicorn = the actual HTTP server that runs Starlette. Together they're maybe 20 KB of dependency surface, both maintained by the same team (Encode), both used in production by tens of thousands of services.

**Why not FastMCP (the popular MCP-specific library):** FastMCP wants you to use its decorator pattern to define tools. Upstream MemPalace already has all 19 tools defined its own way. Adopting FastMCP would mean refactoring the upstream module — which would conflict with every monthly upstream sync (D8). Starlette is library-neutral; we wrap, we don't refactor.

---

### A4 — Single uvicorn worker ✅ LOCKED

**Plain English:** The container runs one worker process (not multiple). A worker is a copy of the app handling requests in parallel. We use one because the wrapper holds a single subprocess (the underlying `mempalace.mcp_server` running on stdio), and that subprocess writes to one ChromaDB. Two workers = two subprocesses = two parallel writers to the same database = data corruption risk.

**Trade-off:** for a single user (you), one worker is plenty. If we ever needed to scale to many simultaneous users (we won't, this is a single-user system), we'd need a different architecture entirely.

---

### A5 — Bearer token stored on laptop at `C:\Users\phatt\.mempalace_client\token` ✅ LOCKED

**Plain English:** The bearer token is a 44-character secret string that authenticates your laptop to the hosted palace. It's stored in a single file on your laptop with restrictive permissions. Each client (Cowork, Claude Code, Claude Desktop) reads from that file or has it pasted in once.

**Why a file and not just an env var:** files persist across reboots and shell sessions; env vars do not (unless set permanently in Windows, which is more friction than it's worth).

**Security note:** this file is the equivalent of a password to your entire memory. Don't paste it in chat unredacted, don't commit it, don't email it. If you ever think it's leaked, we rotate (~3-minute operation, documented in §4 of v0.1).

---

### A6 — `/health` endpoint exposed publicly without auth ✅ LOCKED

**Plain English:** There's a single URL — `mempalace.tstly.dev/health` — that returns "ok" if the service is running and "503" if not. Anyone on the internet can hit it. They learn one bit of information: "the service is up" or "the service is down." That's it.

**Why this is safe:** a healthcheck endpoint is standard practice for monitoring tools (Coolify, Cloudflare, etc.) to verify the service is alive without authenticating. It exposes no palace state, no tool list, nothing about you. The bearer-protected `/mcp` endpoint is where actual functionality lives.

---

### A7 — Auto-bootstrap on first boot ✅ LOCKED

**Plain English:** When the container starts for the first time, the volume is empty. The wrapper detects this and auto-runs `mempalace init` to create the four-wing layout (D3) and writes your identity.txt (D9 Draft C). That way Phase 3 doesn't have a manual setup step — you go from "empty container" to "ready palace" in one boot.

**Trade-off:** the bootstrap logic is small but non-trivial code. The alternative (manual `mempalace init` after deploy) is simpler code, more friction. For a single-user deployment, auto-bootstrap is the right call.

---

### A8 — Resource limits: 1 GB memory, 1.0 CPU ✅ LOCKED (revisit in 1 week)

**Plain English:** Coolify will refuse to give the container more than 1 GB of RAM and one CPU core's worth of compute. ChromaDB's memory usage scales with palace size; for a fresh palace these limits are very generous. After a week of mining, we check actual usage and tighten or loosen.

**What to watch:** if the container starts getting OOM-killed (Out-Of-Memory) after a big mining run, raise the memory limit. If CPU stays pegged, raise CPU. Most likely we'll find 1 GB / 1.0 CPU is overprovisioned and we'll lower to save Coolify resources for other services.

---

## Implementation order (unchanged from v0.1 §11)

1. **2a — wrapper code** (1–2 hrs): write `mempalace/http_server.py`, update `__main__.py`, write `tests/test_http_server.py`. Runs locally via `uvicorn mempalace.http_server:app`.
2. **2b — Dockerfile + local container** (30 min): build, run locally with a temp volume, smoke-test all 5 checks against `localhost:8000` with bearer.
3. **2c — Coolify deploy** (30 min): push image / git-pull-and-build, create service, set env var, attach volume, healthcheck.
4. **2d — tunnel hostname** (15 min): add ingress rule to existing cloudflared config for `mempalace.tstly.dev`, restart tunnel, verify health endpoint.
5. **2e — end-to-end smoke tests** (15 min).

Estimated total: 2.5–4 hrs of focused work. Begins the moment Phase 1 (pytest 85/85) clears.

---

## What changed from v0.1 → v0.2

- A1 confirmed (`tstly.dev` is Matt's domain, locked).
- A2–A8 ratified at v0.1 recommendations.
- Plain-English explanations added per decision so the lock is reviewable without re-reading v0.1's reasoning sections.
- Status banner: DRAFT → LOCKED.

v0.1 is preserved as the rollback anchor.

---

## Body content carried forward unchanged from v0.1

Sections 1 (goal/scope), 2 (high-level architecture diagram), 3 (new code: subprocess-proxy approach + file list + wrapper outline), 4 (bearer-token design details), 5 (container details: Dockerfile + compose + bootstrap), 6 (Cloudflare tunnel routing), 7 (health/observability), 8 (smoke test plan), 9 (risks and mitigations) — all unchanged. See `MemPalace_Phase_2_Architecture_v0.1.md` for the full text.
