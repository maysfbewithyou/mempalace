"""HTTP transport wrapper for the MemPalace MCP server.

version: 0.1
phase: 2a
locked architecture: MemPalace_Phase_2_Architecture_v0.2.md (A1–A8)

Purpose
-------
Upstream `mempalace.mcp_server` is a stdio MCP server (line-delimited JSON-RPC
on stdin/stdout). For the IEP fork's Path A deployment, we expose it over
HTTP behind bearer-token auth so Cowork, Claude Code, and Claude Desktop
(and eventually claude.ai web/mobile/voice via OAuth in Phase 10) can all
query the hosted palace at https://mempalace.tstly.dev .

Design (subprocess-proxy)
-------------------------
We do NOT modify `mempalace.mcp_server`. Instead, this wrapper:
  - Spawns `python -m mempalace.mcp_server --palace <path>` as a long-lived
    child process.
  - Pipes JSON-RPC requests in over stdin, reads responses from stdout.
  - Serializes concurrent HTTP requests via an asyncio.Lock (the upstream
    server is a single-threaded JSON-RPC handler — only one request in
    flight at a time).
  - Auto-restarts the subprocess on crash.

Routes
------
  POST /mcp     — JSON-RPC body in/out. Bearer-auth required.
  GET  /health  — liveness check. Returns "ok" if subprocess responds to
                  an internal ping within 5 s. No auth.

Auth (A5)
---------
  Authorization: Bearer <token>
  Token comes from env var MEMPALACE_BEARER_TOKEN. Constant-time compare
  via secrets.compare_digest. No fallback / no default — service refuses
  to start without the token set.

First-boot bootstrap (A7)
-------------------------
  If MEMPAL_PALACE_PATH's parent directory has no config.json, this
  wrapper creates it on startup with the four-wing layout (D3) and the
  D9 Draft C identity.txt. Idempotent — safe on every restart.

Single uvicorn worker (A4)
--------------------------
  This module assumes one uvicorn worker per container. Multiple workers
  would each spawn their own subprocess, each writing to the same palace.
  Run with: uvicorn mempalace.http_server:app --workers 1 ...
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from .config import MempalaceConfig

# ── Logging ───────────────────────────────────────────────────────────────────
# stdout for app logs (Coolify catches and ships); structured-JSON is a Phase 8+
# concern.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("mempalace.http")


# ── Identity (D9 Draft C, ~95 tokens, locked) ────────────────────────────────
# Source of truth for the L0 identity layer. Written to identity.txt on first
# boot if not present. To revise: bump fork version, regenerate, document.
IDENTITY_TEXT = (
    "I am Matt Mays' memory palace. Matt operates MEGA Entertainment (parent\n"
    "corp), runs IEP — Interactive Event Productions — for event production\n"
    "ops, and is building Atlas, the internal software system across the\n"
    "businesses. Four wings: wing_mega (corporate), wing_iep (events ops),\n"
    "wing_atlas (software / dev), wing_personal. Twelve halls common to every\n"
    "wing: events, venues, vendors, timelines, budgets, team, clients,\n"
    "productions, equipment, creative, technical, and the always-present diary.\n"
    "Save verbatim — never summarize, never paraphrase. Always search the palace\n"
    "before answering questions about Matt's work.\n"
)


# ── Configuration knobs (env-var driven) ─────────────────────────────────────
def _get_bearer_token() -> str:
    """Required env var. Service refuses to start if unset.

    Refusal-to-start is by design — running without auth on a public tunnel
    is never the right answer. Operator must set the token before deploy.
    """
    token = os.environ.get("MEMPALACE_BEARER_TOKEN")
    if not token or len(token) < 16:
        raise RuntimeError(
            "MEMPALACE_BEARER_TOKEN env var is required and must be >=16 chars. "
            "Generate via: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    return token


def _get_palace_path() -> Path:
    """Where the ChromaDB palace lives inside the container.

    Defaults to /data/.mempalace/palace (Hardening Fix #14: must be under HOME,
    and HOME=/data inside the container per Dockerfile).
    """
    return Path(os.environ.get("MEMPAL_PALACE_PATH", "/data/.mempalace/palace"))


def _get_subprocess_cmd() -> list[str]:
    """Command to spawn the upstream stdio MCP server.

    Override via MEMPALACE_SUBPROCESS_CMD for testing (e.g., point at a fake
    script). Default uses the same Python that's running this wrapper.
    """
    override = os.environ.get("MEMPALACE_SUBPROCESS_CMD")
    if override:
        return override.split()
    return [
        sys.executable,
        "-m",
        "mempalace.mcp_server",
        "--palace",
        str(_get_palace_path()),
    ]


REQUEST_TIMEOUT_SECONDS = float(os.environ.get("MEMPALACE_REQUEST_TIMEOUT", "30"))
HEALTH_TIMEOUT_SECONDS = float(os.environ.get("MEMPALACE_HEALTH_TIMEOUT", "5"))


# ── Bootstrap (A7) ───────────────────────────────────────────────────────────
def bootstrap_if_needed(palace_path: Path) -> None:
    """Idempotent first-boot setup.

    Writes config.json with the four-wing default layout and the D9 identity.txt
    if neither exists. Safe to call on every startup.
    """
    config_dir = palace_path.parent  # ~/.mempalace
    config_dir.mkdir(parents=True, exist_ok=True)

    # Hardening Fix #7: restrictive perms on state directory.
    try:
        os.chmod(config_dir, 0o700)
    except (OSError, NotImplementedError):
        pass  # Windows / non-POSIX falls through

    # config.json — uses upstream's MempalaceConfig.init() which writes
    # defaults including DEFAULT_TOPIC_WINGS (the IEP halls per Personalization #1).
    cfg = MempalaceConfig(config_dir=config_dir)
    cfg.init()
    logger.info("bootstrap: config initialized at %s", cfg._config_file)

    # identity.txt — D9 Draft C content.
    identity_path = config_dir / "identity.txt"
    if not identity_path.exists():
        identity_path.write_text(IDENTITY_TEXT, encoding="utf-8")
        try:
            os.chmod(identity_path, 0o600)  # Hardening Fix #7
        except (OSError, NotImplementedError):
            pass
        logger.info("bootstrap: identity.txt written at %s", identity_path)
    else:
        logger.debug("bootstrap: identity.txt already present at %s", identity_path)


# ── StdioProxy ───────────────────────────────────────────────────────────────
class StdioProxy:
    """Long-lived subprocess wrapping `python -m mempalace.mcp_server`.

    Why subprocess and not in-process import: keeps upstream module untouched
    so monthly D8 sync stays clean. The wrapper is the only thing we own.

    Why a single Lock and not per-request id correlation: simpler. Upstream
    is single-threaded, so concurrent requests must serialize regardless.
    Lock approach keeps stdout-line consumption straightforward.

    Restart policy: on EOF / process exit / json decode error, mark dead
    and lazily restart on the next request. Crashes are logged.
    """

    def __init__(self, cmd: list[str]) -> None:
        self._cmd = cmd
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._started_at: float | None = None
        self._restart_count = 0

    async def start(self) -> None:
        """Spawn the subprocess. Idempotent."""
        if self._proc is not None and self._proc.returncode is None:
            return
        logger.info("stdio_proxy: spawning %s", " ".join(self._cmd))
        self._proc = await asyncio.create_subprocess_exec(
            *self._cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._started_at = asyncio.get_event_loop().time()
        # Drain stderr in the background so it doesn't block the subprocess.
        asyncio.create_task(self._drain_stderr())
        logger.info("stdio_proxy: subprocess pid=%s started", self._proc.pid)

    async def _drain_stderr(self) -> None:
        """Forward subprocess stderr to our logger at INFO."""
        if not self._proc or not self._proc.stderr:
            return
        try:
            while True:
                line = await self._proc.stderr.readline()
                if not line:
                    return
                logger.info("[mcp_server] %s", line.decode("utf-8", "replace").rstrip())
        except Exception as exc:  # noqa: BLE001
            logger.warning("stdio_proxy: stderr drain failed: %s", exc)

    async def stop(self) -> None:
        """Terminate the subprocess gracefully, then forcefully if needed."""
        if not self._proc or self._proc.returncode is not None:
            return
        logger.info("stdio_proxy: stopping pid=%s", self._proc.pid)
        try:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("stdio_proxy: SIGTERM timed out; sending SIGKILL")
                self._proc.kill()
                await self._proc.wait()
        except ProcessLookupError:
            pass
        self._proc = None

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one JSON-RPC request, await one JSON-RPC response.

        Serializes concurrent callers via the lock. On subprocess death,
        attempts a single restart-and-retry; if that fails, raises.
        """
        async with self._lock:
            return await self._request_locked(payload)

    async def notify(self, payload: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (fire-and-forget). No response read.

        Per JSON-RPC 2.0 §4.1, notifications carry no `id` and produce no
        response. We MUST NOT read from stdout here, or we'd consume the
        response of the next real request and crash the session.
        """
        async with self._lock:
            if not self._proc or self._proc.returncode is not None:
                await self._restart()
            proc = self._proc
            assert proc is not None
            assert proc.stdin is not None

            line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
            try:
                proc.stdin.write(line)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                logger.warning("stdio_proxy: notify stdin write failed (%s); restarting", exc)
                await self._restart()

    async def _request_locked(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._proc or self._proc.returncode is not None:
            await self._restart()

        proc = self._proc
        assert proc is not None
        assert proc.stdin is not None
        assert proc.stdout is not None

        # Encode and send
        line = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            proc.stdin.write(line)
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            logger.warning("stdio_proxy: stdin write failed (%s); restarting", exc)
            await self._restart()
            return await self._request_locked(payload)

        # Read one response line, with timeout
        try:
            raw = await asyncio.wait_for(
                proc.stdout.readline(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error("stdio_proxy: response timeout (>%ss); restarting", REQUEST_TIMEOUT_SECONDS)
            await self._restart()
            raise

        if not raw:
            logger.error("stdio_proxy: subprocess EOF; restarting")
            await self._restart()
            return await self._request_locked(payload)

        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("stdio_proxy: invalid JSON from subprocess: %s; raw=%r", exc, raw[:200])
            raise

    async def _restart(self) -> None:
        """Stop (if alive) and re-spawn."""
        await self.stop()
        self._restart_count += 1
        logger.info("stdio_proxy: restart #%d", self._restart_count)
        await self.start()

    async def healthcheck(self) -> bool:
        """Send an MCP `initialize` and return True if a JSON-RPC response comes back in time.

        Used by the /health endpoint. Wraps in its own short timeout.
        """
        ping = {
            "jsonrpc": "2.0",
            "id": "healthcheck",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mempalace-http", "version": "0.1"},
            },
        }
        try:
            resp = await asyncio.wait_for(self.request(ping), timeout=HEALTH_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
            logger.warning("healthcheck: failed (%s)", exc)
            return False
        return isinstance(resp, dict) and resp.get("id") == "healthcheck"


# ── Module-level singletons ──────────────────────────────────────────────────
# Created in lifespan; referenced by route handlers and middleware.
_proxy: StdioProxy | None = None


def _get_proxy() -> StdioProxy:
    if _proxy is None:
        raise RuntimeError("stdio proxy not initialized; lifespan startup did not run")
    return _proxy


# ── Auth middleware ──────────────────────────────────────────────────────────
class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject any request to /mcp without a valid bearer credential.

    Accepts EITHER:
      - The static MEMPALACE_BEARER_TOKEN (for laptop CLI testing / curl diagnostics)
      - An OAuth-issued JWT verified by mempalace.oauth.verify_jwt()
        (for Anthropic Connectors / Cowork / Claude Desktop / claude.ai web+mobile)

    Public paths exempt from auth:
      - /health, /ready                                   (status probes, A6)
      - /oauth/token                                      (OAuth credentials live here)
      - /.well-known/oauth-authorization-server            (RFC 8414 metadata)
      - /.well-known/oauth-protected-resource              (RFC 9728 metadata)

    On 401 we emit a WWW-Authenticate header pointing at the protected-resource
    metadata, per the MCP OAuth spec — this is how Anthropic's connector backend
    discovers our authorization server.
    """

    PUBLIC_PATHS = (
        "/health",
        "/ready",
        "/authorize",  # OAuth 2.0 §4.1.1 — pre-token endpoint, no bearer expected
        "/oauth/token",
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
    )

    def __init__(self, app, expected_token: str) -> None:
        super().__init__(app)
        self._expected = expected_token.encode("utf-8")

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return self._unauth_response(request)

        token_str = header.removeprefix("Bearer ").strip()
        token_bytes = token_str.encode("utf-8")

        # Path 1: static bearer (laptop CLI / diagnostics).
        if secrets.compare_digest(token_bytes, self._expected):
            return await call_next(request)

        # Path 2: OAuth-issued JWT (Anthropic Connectors / Cowork / claude.ai).
        # Lazy-imported so module import doesn't require pyjwt unless OAuth is exercised.
        try:
            from . import oauth as _oauth
            if _oauth.verify_jwt(token_str):
                return await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auth: oauth verify path errored: %s", exc)

        return self._unauth_response(request)

    def _unauth_response(self, request: Request) -> Response:
        """401 with WWW-Authenticate pointing at our protected-resource metadata."""
        scheme_url = f"{request.url.scheme}://{request.url.netloc}"
        www_auth = (
            f'Bearer resource_metadata="{scheme_url}/.well-known/oauth-protected-resource"'
        )
        return JSONResponse(
            {"error": "unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": www_auth},
        )


# ── Route handlers ───────────────────────────────────────────────────────────
async def health(request: Request) -> Response:
    """Lightweight liveness check for Docker / monitoring.

    Returns 200/ok if the wrapper process is alive — does NOT round-trip to
    the StdioProxy subprocess. Reason: ChromaDB's first-time ONNX model load
    can take 30+ seconds; if Docker's healthcheck depended on the subprocess
    being responsive, the container would be killed mid-init in a tight loop.
    Use /ready for the deeper readiness check (round-trips to the subprocess).
    """
    return PlainTextResponse("ok")


async def ready(request: Request) -> Response:
    """Deep readiness check — round-trips to the StdioProxy subprocess.

    Use this from clients that want to know whether the upstream MCP is
    actually responsive (not just whether the wrapper is alive). NOT used
    by Docker's HEALTHCHECK because of the ONNX startup latency described
    in `health`.
    """
    proxy = _get_proxy()
    if await proxy.healthcheck():
        return PlainTextResponse("ready")
    return PlainTextResponse("subprocess unhealthy", status_code=503)


async def mcp(request: Request) -> Response:
    """JSON-RPC over HTTP POST per MCP Streamable HTTP transport.

    Two payload types are handled:
      - Requests (have `id` field): forward to subprocess, return JSON response.
      - Notifications (have `method` but no `id`): forward to subprocess
        fire-and-forget, return 202 Accepted with no body. Required by the MCP
        Streamable HTTP spec — without this, our subprocess proxy would block
        waiting for a response that JSON-RPC notifications never produce, and
        the next legitimate request (e.g. tools/list) would hang or fail.

    v0.1 supports single-message responses only (no SSE streaming); upstream's
    tools all return single results, so JSON suffices.
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            },
            status_code=400,
        )

    if not isinstance(payload, dict):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request: not a JSON object"},
            },
            status_code=400,
        )

    proxy = _get_proxy()

    # Notification (JSON-RPC 2.0 §4.1: Notification = no `id` field).
    # Per MCP Streamable HTTP spec: forward without waiting, return 202 Accepted.
    is_notification = "id" not in payload and "method" in payload
    if is_notification:
        try:
            await proxy.notify(payload)
        except Exception:  # noqa: BLE001
            logger.exception("mcp: notification forward failed (continuing)")
        # 202 Accepted with no body, per spec.
        return Response(status_code=202)

    try:
        response = await proxy.request(payload)
    except asyncio.TimeoutError:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32000, "message": "Subprocess request timed out"},
            },
            status_code=504,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("mcp: unhandled error in subprocess proxy")
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {exc!s}"},
            },
            status_code=500,
        )

    return JSONResponse(response)


# ── Lifespan (startup / shutdown) ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: Starlette):
    """Bootstrap palace state, spawn the proxy, hold it for the app's lifetime."""
    global _proxy

    palace_path = _get_palace_path()
    logger.info("startup: palace_path=%s", palace_path)

    # A7 — first-boot bootstrap.
    bootstrap_if_needed(palace_path)

    # Spawn proxy.
    _proxy = StdioProxy(_get_subprocess_cmd())
    await _proxy.start()
    logger.info("startup complete")

    try:
        yield
    finally:
        logger.info("shutdown: stopping subprocess")
        if _proxy:
            await _proxy.stop()
        logger.info("shutdown complete")


# ── Application factory ──────────────────────────────────────────────────────
def create_app(bearer_token: str | None = None) -> Starlette:
    """Build the Starlette app. Token override is for tests."""
    token = bearer_token if bearer_token is not None else _get_bearer_token()

    # Lazy-import oauth so create_app callers without pyjwt installed (e.g.,
    # narrow unit tests that only exercise /health) don't pay the import cost.
    from . import oauth as _oauth

    return Starlette(
        debug=False,
        routes=[
            # Status probes (no auth)
            Route("/health", health, methods=["GET"]),
            Route("/ready", ready, methods=["GET"]),
            # OAuth 2.0/2.1 endpoints (no bearer required; the auth flow
            # provides its own credentials).
            Route("/authorize", _oauth.authorize_endpoint, methods=["GET"]),
            Route("/oauth/token", _oauth.token_endpoint, methods=["POST"]),
            Route(
                "/.well-known/oauth-authorization-server",
                _oauth.authorization_server_metadata,
                methods=["GET"],
            ),
            Route(
                "/.well-known/oauth-protected-resource",
                _oauth.protected_resource_metadata,
                methods=["GET"],
            ),
            # Bearer-protected MCP (accepts static bearer OR OAuth-issued JWT)
            Route("/mcp", mcp, methods=["POST"]),
        ],
        middleware=[Middleware(BearerAuthMiddleware, expected_token=token)],
        lifespan=lifespan,
    )


# Module-level app for `uvicorn mempalace.http_server:app`.
# Built eagerly: misconfigured env vars (missing/short bearer token) raise at
# import time so uvicorn fails fast with a clear message rather than at first
# request.
#
# Tests that import names from this module before setting the env var should
# either set MEMPALACE_BEARER_TOKEN first (recommended) or use a deferred-import
# pattern. The test suite uses os.environ.setdefault(...) before its
# `from mempalace import http_server` to guarantee the env var is present.
app = create_app()


# ── Entrypoint for `mempalace serve-http` (CLI subcommand) ───────────────────
def run(host: str = "0.0.0.0", port: int = 8000, log_level: str = "info") -> None:
    """Convenience entrypoint for the CLI subcommand.

    For production (Docker), prefer `uvicorn mempalace.http_server:app
    --host 0.0.0.0 --port 8000 --workers 1` directly so uvicorn manages
    signals cleanly.
    """
    import uvicorn  # imported lazily so the module imports without uvicorn installed

    uvicorn.run(
        "mempalace.http_server:app",
        host=host,
        port=port,
        log_level=log_level,
        workers=1,  # A4 — single worker is mandatory
    )
