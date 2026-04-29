# MemPalace — Phase 2 Architecture (v0.1)

Date: 2026-04-27
Status: DRAFT — review and lock before any code lands.

> Phase 2 stands up the hosted MemPalace MCP server on Coolify, fronted by a Cloudflare tunnel at `mempalace.tstly.dev`, behind static bearer-token auth. This document covers the design only — no code, no installs, no commits. Matt reviews this v0.1, we iterate to vN, then we build.

---

## 1. Goal and scope

**In scope for Phase 2:**

- HTTP transport wrapper around `mempalace.mcp_server` (which is stdio-only upstream).
- Static bearer-token authentication.
- Dockerfile + docker-compose service definition for Coolify.
- Persistent volume for the palace data (`/data/.mempalace/`).
- Cloudflare tunnel routing for `mempalace.tstly.dev → coolify-internal-host:port`.
- `/health` endpoint (no auth, for Coolify's healthcheck and external monitoring).
- Smoke-test plan: tunnel reachable → bearer rejects unauth'd → bearer accepts → MCP `initialize` round-trips → one tool call round-trips.

**Explicitly out of scope (deferred or later phases):**

- OAuth — Phase 10 (post-v1.0), once voice-mode tool support is confirmed.
- Anthropic IP allowlisting — Phase 10 (only matters once we open up to claude.ai).
- Rate limiting **above** what `mempalace.mcp_server` already does internally (60 req/min token bucket exists).
- Multi-tenancy / multi-user — not a goal, this is single-user (Matt) only.
- Encryption-at-rest for the palace volume — open issue upstream (#5 in the hardening doc); revisit after v1.0.
- Backups / volume snapshots — covered as Phase 9 closeout-adjacent work, not Phase 2.

---

## 2. High-level architecture

```
                  ┌────────────────────────────────────────────┐
                  │   Cloudflare Edge                           │
                  │   mempalace.tstly.dev (TLS terminated)      │
                  └──────────────┬──────────────────────────────┘
                                 │
                                 │  cloudflared tunnel
                                 │  (origin-side outbound)
                                 │
                  ┌──────────────▼──────────────────────────────┐
                  │   Coolify host (coolify.interactep.app)     │
                  │                                             │
                  │   Docker network: mempalace-net             │
                  │                                             │
                  │   ┌─────────────────────────────────────┐   │
                  │   │  Container: mempalace-http         │   │
                  │   │  ─────────────────────────         │   │
                  │   │  HTTP wrapper (Starlette/FastAPI)   │   │
                  │   │   /mcp           ← Streamable HTTP  │   │
                  │   │   /health        ← liveness         │   │
                  │   │                                     │   │
                  │   │  Spawns subprocess:                 │   │
                  │   │    python -m mempalace.mcp_server   │   │
                  │   │  Pipes JSON-RPC over stdio          │   │
                  │   │                                     │   │
                  │   │  Volume: mempalace_data → /data/    │   │
                  │   │     /data/.mempalace/palace/        │   │
                  │   │     /data/.mempalace/wal/           │   │
                  │   │     /data/.mempalace/identity.txt   │   │
                  │   │     /data/.mempalace/config.json    │   │
                  │   └─────────────────────────────────────┘   │
                  └─────────────────────────────────────────────┘

  Clients (laptop):
    Cowork ─────────┐
    Claude Code ────┼─── Authorization: Bearer <token> ───→ mempalace.tstly.dev/mcp
    Claude Desktop ─┘
```

---

## 3. New code we're adding

**The principle:** keep upstream `mempalace/mcp_server.py` untouched so the monthly upstream sync (D8) stays clean. The HTTP wrapper lives in **new** files, in a sibling location.

### 3.1 Why subprocess-proxy and not in-process

Upstream's `mempalace.mcp_server` is **hand-rolled JSON-RPC over stdio** — it does its own arg parsing, has its own RateLimiter, its own dispatch. It does NOT use the official `mcp.server` SDK or FastMCP. That makes "in-process import the handlers and re-expose" invasive: we'd have to refactor the module to surface handler functions, and that refactor would conflict with every upstream sync.

Subprocess-proxy is cleaner: the wrapper spawns `python -m mempalace.mcp_server` as a child process, pipes JSON-RPC requests to its stdin, reads JSON-RPC responses from its stdout. The upstream module stays a black box; we maintain only the wrapper.

### 3.2 Files to add

| File | Purpose | New / modified |
|---|---|---|
| `mempalace/http_server.py` | Starlette app: `/mcp` (streamable HTTP), `/health`. Bearer-auth middleware. Subprocess management. | NEW |
| `mempalace/__main__.py` | Add a `serve-http` subcommand routing to `http_server:run()`. | MODIFIED (currently 80 bytes, trivial) |
| `pyproject.toml` | Add deps: `starlette>=0.40,<1.0`, `uvicorn>=0.30,<1.0`, `httpx>=0.27` (testing). | MODIFIED |
| `Dockerfile` | Multi-stage build: install package + uvicorn entrypoint. | NEW (root of repo) |
| `docker-compose.coolify.yml` | Coolify-specific compose: env vars, volume mount, healthcheck. | NEW |
| `coolify/cloudflared-config.yml` | Tunnel ingress config snippet. | NEW |
| `tests/test_http_server.py` | Wrapper tests: bearer reject/accept, JSON-RPC round-trip via subprocess. | NEW |

### 3.3 HTTP wrapper outline (pseudocode-level)

```
# mempalace/http_server.py
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio, json, os, secrets

EXPECTED_TOKEN = os.environ["MEMPALACE_BEARER_TOKEN"]   # required, no default
PALACE_PATH = os.environ.get("MEMPAL_PALACE_PATH", "/data/.mempalace/palace")

class BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)         # health is unauth'd
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        token = auth.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(token, EXPECTED_TOKEN):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

class StdioProxy:
    """Long-lived subprocess: python -m mempalace.mcp_server --palace <path>
       Forwards JSON-RPC over stdin/stdout, line-delimited."""
    async def start(self): ...
    async def request(self, payload: dict) -> dict: ...
    async def stop(self): ...

proxy = StdioProxy()

async def health(request): return PlainTextResponse("ok")

async def mcp(request):
    # Streamable HTTP transport: client POSTs JSON-RPC, we respond with JSON-RPC
    # (or, for tool calls that stream, with NDJSON frames).
    payload = await request.json()
    response = await proxy.request(payload)
    return JSONResponse(response)

app = Starlette(
    routes=[Route("/health", health), Route("/mcp", mcp, methods=["POST"])],
    middleware=[Middleware(BearerAuth)],
    on_startup=[proxy.start],
    on_shutdown=[proxy.stop],
)
```

This is a sketch — actual `StdioProxy` needs care around concurrent requests (stdio is single-stream so we serialize via an `asyncio.Lock` or per-request id correlation). I'll spell out the concurrency model in v0.2 of this doc once we lock the high-level shape.

---

## 4. Bearer-token auth design

**Generation:** 32 random bytes, base64-encoded → 44-character token. Generated once via `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

**Storage:** Coolify env var `MEMPALACE_BEARER_TOKEN`, set on the service. The token never enters the container image, never enters `git`, never enters chat unredacted.

**Distribution to clients:** I document the token's location in a non-committed `.env.local` on Matt's laptop (path: `C:\Users\phatt\.mempalace_client\token`, file mode `0o600` equivalent on Windows). Each client (Cowork MCP config, Claude Code, Claude Desktop) reads from that file or has the token pasted in once.

**Rotation:** generate a new token, update Coolify env var, update each client config. ~3-minute operation. No automated rotation in v1.0.

**Token check is constant-time** (`secrets.compare_digest`) to avoid timing-attack leakage.

---

## 5. Container design

### 5.1 Dockerfile

- Base: `python:3.12-slim` (3.12 — chromadb 0.5.x is best-tested on 3.10–3.12; 3.14 on host is fine but in-container we pin to a stable line).
- Non-root user: `mempalace:1000`.
- `WORKDIR /app`, copy package, `pip install -e .` (or `pip install .` if we publish the wheel).
- `ENV HOME=/data` so Hardening Fix #14 (`MEMPAL_DIR` must be under `$HOME`) is satisfied with `MEMPAL_DIR=/data/.mempalace/palace`.
- `EXPOSE 8000`.
- `CMD ["uvicorn", "mempalace.http_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`. **Single worker** because the StdioProxy holds a single subprocess; multiple uvicorn workers would each spawn their own subprocess, each writing to the same palace, which we DON'T want.

### 5.2 docker-compose for Coolify

| Setting | Value |
|---|---|
| Service name | `mempalace-http` |
| Image | built from this fork's Dockerfile |
| Volumes | `mempalace_data:/data` |
| Env vars | `MEMPALACE_BEARER_TOKEN` (secret), `MEMPAL_PALACE_PATH=/data/.mempalace/palace`, `PYTHONUNBUFFERED=1`, `LOG_LEVEL=INFO` |
| Healthcheck | `curl -fsS http://localhost:8000/health \|\| exit 1` every 30s, 3 retries |
| Restart policy | `unless-stopped` |
| Resource limits | mem 1 GB / cpu 1.0 (revisit after a week of mining) |
| Network | Coolify's internal proxy network |

### 5.3 First-boot bootstrap

The volume starts empty on first deploy. The HTTP wrapper's startup hook runs:

1. If `/data/.mempalace/` doesn't exist → run `mempalace init /data/seed` (a one-line Python invocation in the entrypoint script) to create config.json with our four-wing layout per D3.
2. If `/data/.mempalace/identity.txt` doesn't exist → write the D9-locked Draft C content, file-mode `0o600`.
3. Spawn the StdioProxy subprocess.

Phase 3 covers the post-init steps (verify wings, etc.) once the container is up.

---

## 6. Cloudflare tunnel routing

Existing tunnel infra: `coolify.interactep.app` is already on a Cloudflare tunnel; presumably a wildcard `*.tstly.dev` or `*.interactep.app` or an explicit hostname list.

**Question for Matt:** is `tstly.dev` a domain you own / control, and is the tunnel currently configured for it? If yes, we add a hostname rule:

```yaml
# coolify/cloudflared-config.yml (snippet to merge into existing tunnel config)
ingress:
  - hostname: mempalace.tstly.dev
    service: http://mempalace-http:8000
  # ... existing rules continue
```

If `tstly.dev` is not wired, the alternatives are: use a subdomain on a domain that IS wired (e.g., `mempalace.interactep.app`), or configure the new domain on Cloudflare and point a tunnel hostname at it.

I'll defer this to a sub-decision in v0.2 of this doc once you tell me which domain is on hand.

---

## 7. Health and observability

- **`/health`** returns `200 OK` with body `ok` if the wrapper is up AND the StdioProxy subprocess responds to a `ping`-style internal call within 5 s. Returns `503` otherwise.
- Logs: stdout-only (Coolify catches and ships to its log viewer). Structured JSON logs would be nicer but are a Phase 8+ concern.
- Metrics: out of scope for v1.0. Open issue post-launch.
- Hook log on the **host laptop** (`~/.mempalace/hook_state/hook.log`) is unrelated to the container — that's the local hooks' own log, kept on Matt's machine, used by the weekly hook-review scheduled task.

---

## 8. Test plan (smoke tests, not full pytest)

Once deployed, we verify in this order:

1. `curl -sS https://mempalace.tstly.dev/health` → `200 ok`. Confirms tunnel + container alive.
2. `curl -sS https://mempalace.tstly.dev/mcp` (no auth) → `401`. Confirms bearer middleware works.
3. `curl -sS -H "Authorization: Bearer <token>" -X POST https://mempalace.tstly.dev/mcp -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'` → valid MCP `initialize` response. Confirms wrapper proxies correctly.
4. Repeat (3) with `method: "tools/list"` → returns the upstream's `mempalace_*` tool list. Confirms StdioProxy is round-tripping.
5. From Cowork: register the bearer-MCP, call `mempalace_status` → returns palace stats (empty palace expected; that's fine).

If all 5 pass, Phase 2 is done and Phase 3 (`mempalace init` + identity.txt + wing creation) starts.

---

## 9. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| StdioProxy subprocess crashes mid-request | Medium | Wrapper returns 500 until subprocess restarts | Auto-restart on crash; log every restart; consider supervisor pattern in v0.2 |
| Concurrent requests to single subprocess interleave responses | High if not serialized | JSON-RPC client confusion | Serialize via `asyncio.Lock` initially; switch to JSON-RPC `id` correlation if perf demands |
| Container restart loses in-flight ChromaDB writes | Low (ChromaDB has WAL) | Data loss on partial commit | Volume mount + ChromaDB's own WAL handle this; document the recovery path |
| Bearer token leaks (paste in chat, commit, etc.) | Medium (human factor) | Full palace read/write | Token rotation procedure documented; `.gitignore` covers `.env*`; Cowork redaction help |
| Coolify host outage | Low | All clients lose memory access | Single-host single-instance is accepted v1.0 risk; v2 considers replica or local fallback |
| Upstream `mempalace.mcp_server` changes its stdio contract | Low (stable interface) | Wrapper breaks until updated | Monthly D8 sync flags `mcp_server.py` as CONFLICT-RISK; we catch it before merge |

---

## 10. Decisions you (Matt) need to ratify before I write code

| # | Decision | Recommended default |
|---|---|---|
| **A1** | Domain for the tunnel | `mempalace.tstly.dev` (per kickoff) — confirm it's a domain you own and have on the existing Cloudflare tunnel. If not, suggest an alternative. |
| **A2** | Container Python version | `python:3.12-slim` (chromadb 0.5.x best-tested) |
| **A3** | Wrapper transport library | Starlette + uvicorn (lightweight, well-known, no extra magic) |
| **A4** | Single uvicorn worker | YES (StdioProxy is single-subprocess; multi-worker breaks palace consistency) |
| **A5** | Bearer-token storage on laptop | `C:\Users\phatt\.mempalace_client\token` file, mode `0o600` equivalent |
| **A6** | `/health` exposed publicly without auth | YES (standard practice; only returns `ok`/`503`, no palace state) |
| **A7** | Bootstrap behavior on first boot | YES — auto-run `mempalace init` + write identity.txt if volume is empty |
| **A8** | Resource limits | 1 GB memory / 1.0 CPU; revisit in a week |

If any of A1–A8 should be different, call them out and I'll iterate v0.2 of this doc before writing a line of code.

---

## 11. Implementation phases (within Phase 2)

When you green-light this design:

1. **2a — wrapper code in fork** (1–2 hrs): write `http_server.py`, `__main__.py` update, tests. Runs locally via `uvicorn mempalace.http_server:app` against a local palace. No Docker yet.
2. **2b — Dockerfile + local container** (30 min): build, run locally with a temp volume, smoke-test all 5 checks against `localhost:8000` with bearer.
3. **2c — Coolify deploy** (30 min): push image (or git-pull-and-build on Coolify), create service, set env var, attach volume, healthcheck.
4. **2d — Tunnel hostname** (15 min): add ingress rule to existing cloudflared config, restart tunnel, verify `https://mempalace.tstly.dev/health` returns `ok`.
5. **2e — End-to-end smoke tests** (15 min): the 5 checks from §8.

Estimated total wall time: 2.5–4 hrs of focused work.

---

## 12. What you do next

Read this doc. Push back on anything you don't like — A1–A8 in §10 in particular, since those drive the code. Once we lock v0.x as final, I move to writing 2a.

Open question loose ends:
- Is `tstly.dev` already on a Cloudflare tunnel from your Coolify? (A1)
- Anything else you want to flag before I generate v0.2?
