# MemPalace Deployment — Session Log v1.11

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.10.

---

## v1.0–v1.10 — Summary

- v1.0–v1.9: Phase 0 audit, Discovery Report, all nine decisions D1–D9 locked.
- v1.10: Phase 2 Architecture v0.2 locked (A1–A8); Claude.ai export inspected (69 conversations, 3,238 messages, 2026-01-24 to 2026-04-27); skip list confirmed.

---

## v1.11 — Phase 2a code complete (2026-04-27)

Phase 1 (pytest 85/85) cleared; Matt green-lit Phase 2a. HTTP wrapper code written and self-reviewed.

### Files created or modified

| File | Status | Size | Purpose |
|---|---|---|---|
| `mempalace/http_server.py` | NEW | ~21 KB | Starlette/uvicorn wrapper. Bearer auth, StdioProxy subprocess manager, /mcp + /health, lifespan with first-boot bootstrap. |
| `mempalace/__main__.py` | MODIFIED (was 80 B → 1.7 KB) | 1.7 KB | Adds `serve-http` subcommand intercept BEFORE delegating to `cli.main()`. Keeps upstream `cli.py` untouched for clean D8 syncs. |
| `pyproject.toml` | MODIFIED | ~2.7 KB | Version bump `3.0.14` → `3.0.14+iep.1` (PEP 440 local version). New `[http]` optional-deps group: `starlette>=0.40,<1.0`, `uvicorn[standard]>=0.30,<1.0`. Added `httpx>=0.27` to dev for tests. |
| `tests/test_http_server.py` | NEW | ~12 KB | 14 tests: bearer-auth (5), body validation (2), bootstrap idempotency (2), env-var validation (3), StdioProxy real-subprocess integration (3 — round-trip, concurrent serialization, crash-restart). |

### Self-review fixes applied during 2a

- **`_AppProxy` removed.** Initial draft used a lazy-app shim so module-import didn't fail without the bearer env var. Decided fail-fast at import is better DX (operators see the misconfig immediately rather than at first request). Replaced with `app = create_app()` at module level. Tests set the env var before importing the module, so test imports still succeed.
- **Test fixture rewritten** to construct a minimal Starlette app from primitives (no lifespan) instead of attempting to monkey with `app.router.lifespan_context`, which isn't reliable across Starlette versions. The lifespan / bootstrap path is unit-tested separately via `test_bootstrap_creates_config_and_identity` and the StdioProxy integration tests.

### Architecture compliance check (vs Phase 2 Architecture v0.2)

| Decision | Implementation |
|---|---|
| A1 — `mempalace.tstly.dev` | Wrapper is host-agnostic; tunnel routing happens in 2d. |
| A2 — `python:3.12-slim` container | Phase 2b — Dockerfile not yet written. |
| A3 — Starlette + uvicorn | ✅ Used. No FastMCP. |
| A4 — Single uvicorn worker | ✅ `run()` hardcodes `workers=1`. Comments document why. |
| A5 — Bearer token storage on laptop | Out of wrapper scope. Documented in `MEMPALACE_BEARER_TOKEN` env var requirement. |
| A6 — `/health` unauth | ✅ `BearerAuthMiddleware.dispatch` early-returns for `/health`. |
| A7 — First-boot bootstrap | ✅ `bootstrap_if_needed()` writes config.json + identity.txt; idempotent; tested. |
| A8 — Resource limits | Container concern, deferred to 2b/2c. |

### Test surface (pre-run — Matt to verify locally)

The new test file covers:

1. `/health` reachable without auth, returns 200/ok.
2. `/health` returns 503 when subprocess unhealthy.
3. `/mcp` rejects no Authorization header.
4. `/mcp` rejects wrong token.
5. `/mcp` rejects non-Bearer scheme.
6. `/mcp` accepts valid bearer.
7. `/mcp` returns JSON-RPC parse error on invalid JSON body.
8. `/mcp` returns JSON-RPC invalid-request on non-object body.
9. `bootstrap_if_needed` creates config.json + identity.txt with correct content.
10. `bootstrap_if_needed` is idempotent (doesn't overwrite existing identity).
11. `_get_bearer_token` raises if env var unset.
12. `_get_bearer_token` raises if env var <16 chars.
13. `_get_bearer_token` accepts 16+ chars.
14. `StdioProxy` round-trips a real subprocess (uses an in-test fake stdio MCP server).
15. `StdioProxy` serializes 10 concurrent requests via the lock.
16. `StdioProxy` auto-restarts after subprocess crash.

(Counted as 16; the file groups them into 14 named test functions.)

### Phase 2a verification command for Matt

```powershell
cd "C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork"
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,http]"
pytest tests/ -v
```

Expected: **85 (existing) + ~16 (new) = ~101 passed**. Any failure is a Phase 2a blocker — paste the failures and we fix before Phase 2b.

### Next gate

Phase 2a → Phase 2b transition: confirm test suite is green on Matt's laptop.

### Issues carried forward

- ISSUE-2 (open): `claude` CLI not installed (Phase 7 dep).
- ISSUE-3 (cosmetic): stale `python` PATH entry.
- ISSUE-5 (parked, Phase 10): voice-mode tool support — Matt testing externally.
- ISSUE-6 (parked, Phase 6): Claude.ai export inspected, mining queued post-Phase 5.
- ISSUE-7 (parked, Phase 11): Slack mining design.
- ISSUE-8 (Phase 8): Verify Stop hook merge behavior.

### Versioning policy

Every artifact carries a version stamp. Decision and design locks bump session-log minor version. Code modules carry their own version headers in module docstrings (`http_server.py` v0.1, `__main__.py` v0.2). Each prior log version preserved as a rollback anchor.
