"""Tests for the IEP fork's HTTP/MCP wrapper.

version: 0.3
phase: 2a (extended)
covers: mempalace.http_server (incl. v0.2 buffer-corruption fix and v0.3
        large-response LimitOverrunError fix)
rollback: revert to 0.2 by deleting the "v0.3 large response" test section.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# Skip the whole module if starlette isn't available — the [http] extra is
# optional. CI / dev environments that have it installed will run these tests;
# environments that don't will silently skip.
pytest.importorskip("starlette")
pytest.importorskip("httpx")

from starlette.testclient import TestClient  # noqa: E402

# Set required env var BEFORE importing the wrapper module (the module reads
# it at app-construction time via _get_bearer_token()).
os.environ.setdefault("MEMPALACE_BEARER_TOKEN", "test-token-aaaaaaaaaaaaaaaaaaaa")

from mempalace import http_server  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────


class FakeProxy:
    """In-memory stand-in for StdioProxy. Records calls, returns canned responses."""

    def __init__(self, healthy: bool = True, response_overrides: dict | None = None):
        self.healthy = healthy
        self.calls: list[dict] = []
        self.overrides = response_overrides or {}

    async def request(self, payload: dict) -> dict:
        self.calls.append(payload)
        method = payload.get("method", "")
        if method in self.overrides:
            return self.overrides[method]
        return {
            "jsonrpc": "2.0",
            "id": payload.get("id"),
            "result": {"echoed_method": method},
        }

    async def healthcheck(self) -> bool:
        return self.healthy

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


@pytest.fixture
def fake_proxy():
    return FakeProxy(healthy=True)


@pytest.fixture
def app_with_fake(fake_proxy, monkeypatch):
    """Build a minimal Starlette app for route + middleware tests.

    Critically: we do NOT call create_app() (which wires the real lifespan that
    would bootstrap state and spawn a real subprocess). Instead we construct
    the app from the same primitives create_app uses, but with no lifespan.
    The fake proxy is injected as the module-level _proxy so route handlers
    that call _get_proxy() see the fake.
    """
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route

    monkeypatch.setattr(http_server, "_proxy", fake_proxy)

    test_app = Starlette(
        debug=False,
        routes=[
            Route("/health", http_server.health, methods=["GET"]),
            Route("/mcp", http_server.mcp, methods=["POST"]),
        ],
        middleware=[
            Middleware(
                http_server.BearerAuthMiddleware,
                expected_token="test-token-aaaaaaaaaaaaaaaaaaaa",
            )
        ],
    )

    # Use TestClient WITHOUT the `with` context manager so no lifespan events fire.
    yield TestClient(test_app)


VALID_AUTH = {"Authorization": "Bearer test-token-aaaaaaaaaaaaaaaaaaaa"}


# ── Auth tests ────────────────────────────────────────────────────────────────


def test_health_does_not_require_auth(app_with_fake):
    r = app_with_fake.get("/health")
    assert r.status_code == 200
    assert r.text == "ok"


def test_health_returns_200_even_when_subprocess_unhealthy(monkeypatch):
    """`/health` is a lightweight liveness check — it does NOT round-trip to the
    StdioProxy. So even when the subprocess is unhealthy, /health returns 200.
    The deep check is /ready (separate test below)."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route

    fake = FakeProxy(healthy=False)
    monkeypatch.setattr(http_server, "_proxy", fake)

    test_app = Starlette(
        debug=False,
        routes=[Route("/health", http_server.health, methods=["GET"])],
        middleware=[
            Middleware(
                http_server.BearerAuthMiddleware,
                expected_token="x" * 32,
            )
        ],
    )

    client = TestClient(test_app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.text == "ok"


def test_ready_returns_200_when_subprocess_healthy(monkeypatch):
    """`/ready` is the deep readiness check — round-trips to StdioProxy."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route

    fake = FakeProxy(healthy=True)
    monkeypatch.setattr(http_server, "_proxy", fake)

    test_app = Starlette(
        debug=False,
        routes=[Route("/ready", http_server.ready, methods=["GET"])],
        middleware=[
            Middleware(
                http_server.BearerAuthMiddleware,
                expected_token="x" * 32,
            )
        ],
    )

    client = TestClient(test_app)
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.text == "ready"


def test_ready_returns_503_when_subprocess_unhealthy(monkeypatch):
    """`/ready` returns 503 when the StdioProxy can't get a response."""
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.routing import Route

    fake = FakeProxy(healthy=False)
    monkeypatch.setattr(http_server, "_proxy", fake)

    test_app = Starlette(
        debug=False,
        routes=[Route("/ready", http_server.ready, methods=["GET"])],
        middleware=[
            Middleware(
                http_server.BearerAuthMiddleware,
                expected_token="x" * 32,
            )
        ],
    )

    client = TestClient(test_app)
    r = client.get("/ready")
    assert r.status_code == 503


def test_mcp_rejects_no_auth(app_with_fake):
    r = app_with_fake.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_mcp_rejects_wrong_token(app_with_fake):
    r = app_with_fake.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Authorization": "Bearer wrongtoken-zzzzzzzzzzzzzzzzz"},
    )
    assert r.status_code == 401


def test_mcp_rejects_non_bearer_scheme(app_with_fake):
    r = app_with_fake.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Authorization": "Basic test-token-aaaaaaaaaaaaaaaaaaaa"},
    )
    assert r.status_code == 401


def test_mcp_accepts_valid_bearer(app_with_fake, fake_proxy):
    r = app_with_fake.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 42, "method": "tools/list"},
        headers=VALID_AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 42
    assert "result" in body
    assert len(fake_proxy.calls) == 1
    assert fake_proxy.calls[0]["method"] == "tools/list"


def test_mcp_accepts_oauth_jwt(app_with_fake, fake_proxy, monkeypatch):
    """Phase 10: OAuth-issued JWT should authenticate just like static bearer.

    Confirms BearerAuthMiddleware's path 2 (JWT verification via mempalace.oauth)
    is wired and accepts a freshly-issued token from oauth.issue_jwt().
    """
    pytest.importorskip("jwt")
    monkeypatch.setenv("MEMPALACE_OAUTH_CLIENT_ID", "test-client-id-1234567890aaaa")
    monkeypatch.setenv("MEMPALACE_OAUTH_CLIENT_SECRET", "test-client-secret-1234567890aaaa")
    monkeypatch.setenv("MEMPALACE_OAUTH_JWT_SECRET", "x" * 64)
    monkeypatch.setenv("MEMPALACE_OAUTH_ISSUER", "https://test.example/")

    from mempalace import oauth as _oauth

    jwt_token, _ttl = _oauth.issue_jwt("test-client-id-1234567890aaaa")
    r = app_with_fake.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 99, "method": "tools/list"},
        headers={"Authorization": f"Bearer {jwt_token}"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == 99


def test_mcp_emits_www_authenticate_on_unauth(app_with_fake):
    """401 responses must include WWW-Authenticate pointing at the protected-resource
    metadata, per the MCP OAuth spec — that's how Anthropic's connector backend
    discovers our authorization server."""
    r = app_with_fake.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert r.status_code == 401
    www_auth = r.headers.get("www-authenticate", "")
    assert "Bearer" in www_auth
    assert "resource_metadata=" in www_auth
    assert "/.well-known/oauth-protected-resource" in www_auth


# ── Body validation ───────────────────────────────────────────────────────────


def test_mcp_returns_parse_error_on_invalid_json(app_with_fake):
    r = app_with_fake.post(
        "/mcp",
        content=b"this is not json",
        headers={**VALID_AUTH, "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == -32700  # JSON-RPC parse error code


def test_mcp_returns_invalid_request_on_non_object_body(app_with_fake):
    r = app_with_fake.post(
        "/mcp",
        json=["not", "an", "object"],
        headers=VALID_AUTH,
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == -32600


# ── Bootstrap tests (A7) ──────────────────────────────────────────────────────


def test_bootstrap_creates_config_and_identity(tmp_path):
    palace_path = tmp_path / ".mempalace" / "palace"
    http_server.bootstrap_if_needed(palace_path)

    config_dir = palace_path.parent
    assert config_dir.exists()
    assert (config_dir / "config.json").exists()
    assert (config_dir / "identity.txt").exists()
    identity = (config_dir / "identity.txt").read_text(encoding="utf-8")
    assert "Matt Mays' memory palace" in identity
    assert "wing_mega" in identity
    assert "wing_iep" in identity
    assert "wing_atlas" in identity
    assert "wing_personal" in identity


def test_bootstrap_idempotent(tmp_path):
    palace_path = tmp_path / ".mempalace" / "palace"
    http_server.bootstrap_if_needed(palace_path)

    identity_path = palace_path.parent / "identity.txt"
    original_mtime = identity_path.stat().st_mtime

    # Tamper to ensure bootstrap doesn't overwrite an existing identity file.
    identity_path.write_text("CUSTOMIZED\n", encoding="utf-8")

    http_server.bootstrap_if_needed(palace_path)

    assert identity_path.read_text(encoding="utf-8") == "CUSTOMIZED\n"


# ── Bearer token validation (env-var hardening) ───────────────────────────────


def test_bearer_token_required_at_startup(monkeypatch):
    monkeypatch.delenv("MEMPALACE_BEARER_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="MEMPALACE_BEARER_TOKEN"):
        http_server._get_bearer_token()


def test_bearer_token_rejects_too_short(monkeypatch):
    monkeypatch.setenv("MEMPALACE_BEARER_TOKEN", "short")
    with pytest.raises(RuntimeError, match=">=16"):
        http_server._get_bearer_token()


def test_bearer_token_accepts_min_length(monkeypatch):
    monkeypatch.setenv("MEMPALACE_BEARER_TOKEN", "x" * 16)
    assert http_server._get_bearer_token() == "x" * 16


# ── StdioProxy integration test (real subprocess, fake server) ───────────────


@pytest.fixture
def fake_stdio_server_script(tmp_path):
    """A tiny Python script that mimics the upstream stdio MCP server's
    line-delimited JSON-RPC contract. Echoes back any request as a result.
    """
    script = tmp_path / "fake_mcp_server.py"
    script.write_text(textwrap.dedent("""
        import json, sys
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except Exception:
                continue
            resp = {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {"echoed": req.get("method", "")},
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
    """))
    return script


def test_stdio_proxy_round_trip(fake_stdio_server_script):
    """Spawn a real subprocess, send one request, get one response, terminate."""

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(fake_stdio_server_script)])
        await proxy.start()
        try:
            resp = await proxy.request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            assert resp["id"] == 1
            assert resp["result"]["echoed"] == "tools/list"
        finally:
            await proxy.stop()

    asyncio.run(run())


def test_stdio_proxy_serializes_concurrent_requests(fake_stdio_server_script):
    """Fire 10 requests concurrently; all should get correct responses."""

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(fake_stdio_server_script)])
        await proxy.start()
        try:
            payloads = [
                {"jsonrpc": "2.0", "id": i, "method": f"method_{i}"}
                for i in range(10)
            ]
            responses = await asyncio.gather(*[proxy.request(p) for p in payloads])
            # Each response must echo its own method back. The lock guarantees
            # we don't get crossed wires.
            ids = sorted(r["id"] for r in responses)
            assert ids == list(range(10))
            for r in responses:
                assert r["result"]["echoed"] == f"method_{r['id']}"
        finally:
            await proxy.stop()

    asyncio.run(run())


def test_stdio_proxy_handles_subprocess_crash(tmp_path):
    """If the subprocess exits, the proxy should auto-restart on next request."""
    crashing_script = tmp_path / "crashing.py"
    # First call: print response then exit. Second call: would never get
    # the chance because subprocess is dead — proxy restarts and we get
    # the same first-call behavior again.
    crashing_script.write_text(textwrap.dedent("""
        import json, sys
        line = sys.stdin.readline().strip()
        if line:
            req = json.loads(line)
            resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": "first"}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        sys.exit(0)
    """))

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(crashing_script)])
        await proxy.start()
        try:
            r1 = await proxy.request({"jsonrpc": "2.0", "id": 1, "method": "x"})
            assert r1["result"] == "first"
            # Subprocess has now exited. Next request triggers restart.
            r2 = await proxy.request({"jsonrpc": "2.0", "id": 2, "method": "x"})
            assert r2["result"] == "first"
            assert proxy._restart_count >= 1
        finally:
            await proxy.stop()

    asyncio.run(run())


# ── v0.2 buffer corruption regression tests ─────────────────────────────────
#
# These tests guard the StdioProxy fix landed in http_server.py v0.2. The
# original bug: when a previous request's readline() was canceled (typically
# by a healthcheck wait_for firing during a slow chromadb cold-start), the
# in-flight response could land in the asyncio StreamReader buffer AFTER
# cancellation. The next legitimate request would then consume that orphan
# response as its own — surfacing in claude.ai as a "wrong-shape" tool result
# (e.g. mempalace_kg_query receiving the previous tool's status payload).
#
# The fix has three parts: (a) JSON-RPC id correlation in _request_locked
# loops past orphans up to MAX_ORPHAN_RESPONSES; (b) healthcheck() restarts
# the subprocess on outer timeout; (c) REQUEST_TIMEOUT_SECONDS bumped to 120s
# so chromadb cold-start no longer triggers spurious restarts.


def test_stdio_proxy_discards_orphan_response_with_wrong_id(tmp_path):
    """Subprocess emits an unrelated response BEFORE the real one (simulating
    a leftover from a canceled earlier request). Proxy must skip it and
    return the real response, not the orphan."""
    script = tmp_path / "leaky_server.py"
    script.write_text(textwrap.dedent("""
        import json, sys
        # Pre-emit an orphan response with a stale id (simulates the leftover
        # from a previous request whose readline was canceled).
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0",
            "id": "stale-orphan",
            "result": {"echoed": "stale_method"},
        }) + "\\n")
        sys.stdout.flush()
        # Now act normally.
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            resp = {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {"echoed": req.get("method", "")},
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
    """))

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(script)])
        await proxy.start()
        try:
            resp = await proxy.request(
                {"jsonrpc": "2.0", "id": "real-1", "method": "tools/list"}
            )
            # MUST get the real response, not the stale orphan.
            assert resp["id"] == "real-1", f"Got orphan instead of real: {resp}"
            assert resp["result"]["echoed"] == "tools/list"
        finally:
            await proxy.stop()

    asyncio.run(run())


def test_stdio_proxy_discards_multiple_orphans_then_returns_real(tmp_path):
    """Subprocess emits 3 orphans before responding correctly — proxy should
    walk past all of them up to MAX_ORPHAN_RESPONSES."""
    script = tmp_path / "multi_orphan_server.py"
    script.write_text(textwrap.dedent("""
        import json, sys
        # Emit 3 orphans first.
        for i in range(3):
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": f"orphan-{i}",
                "result": {"echoed": f"orphan_method_{i}"},
            }) + "\\n")
            sys.stdout.flush()
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            resp = {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {"echoed": req.get("method", "")},
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
    """))

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(script)])
        await proxy.start()
        try:
            resp = await proxy.request(
                {"jsonrpc": "2.0", "id": "real-2", "method": "real_method"}
            )
            assert resp["id"] == "real-2", f"Got orphan: {resp}"
            assert resp["result"]["echoed"] == "real_method"
        finally:
            await proxy.stop()

    asyncio.run(run())


def test_stdio_proxy_restarts_after_too_many_orphans(tmp_path):
    """If the subprocess emits more than MAX_ORPHAN_RESPONSES garbage replies,
    the proxy gives up, raises, and triggers a restart (so the next caller
    gets a fresh subprocess instead of being stuck in a bad state)."""
    n_orphans = http_server.MAX_ORPHAN_RESPONSES + 2
    script = tmp_path / "spam_server.py"
    script.write_text(textwrap.dedent(f"""
        import json, sys
        # Emit MAX_ORPHAN_RESPONSES + 2 garbage responses, then go silent.
        for i in range({n_orphans}):
            sys.stdout.write(json.dumps({{
                "jsonrpc": "2.0",
                "id": f"spam-{{i}}",
                "result": "x",
            }}) + "\\n")
            sys.stdout.flush()
        # Drain stdin but never respond.
        for line in sys.stdin:
            pass
    """))

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(script)])
        await proxy.start()
        try:
            with pytest.raises(RuntimeError, match="orphan"):
                await proxy.request(
                    {"jsonrpc": "2.0", "id": "real", "method": "x"}
                )
            # The proxy should have triggered _restart() inside the failure
            # path so the next legitimate caller gets a clean subprocess.
            assert proxy._restart_count >= 1
        finally:
            await proxy.stop()

    asyncio.run(run())


def test_healthcheck_outer_timeout_triggers_restart(tmp_path, monkeypatch):
    """If healthcheck()'s outer wait_for fires while the subprocess is still
    computing, the proxy must restart so any in-flight response can't poison
    the buffer for the next legitimate caller."""
    # Subprocess that takes 2s before responding — too slow for the tiny
    # healthcheck timeout we're about to set, but fast enough to keep the
    # test quick.
    slow = tmp_path / "slow_init.py"
    slow.write_text(textwrap.dedent("""
        import json, sys, time
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            time.sleep(2.0)
            resp = {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {"echoed": req.get("method", "")},
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
    """))

    # Force a tiny healthcheck timeout so we don't have to wait long.
    monkeypatch.setattr(http_server, "HEALTH_TIMEOUT_SECONDS", 0.3)

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(slow)])
        await proxy.start()
        try:
            healthy = await proxy.healthcheck()
            assert healthy is False  # outer timeout fired
            # v0.2 contract: the timeout path should have called _restart().
            assert proxy._restart_count >= 1, (
                "healthcheck timeout did not trigger restart — buffer state "
                "could leak to the next caller"
            )
        finally:
            await proxy.stop()

    asyncio.run(run())


# ── v0.3 large-response regression test ────────────────────────────────────
#
# Guards the StdioProxy fix landed in http_server.py v0.3. Asyncio's
# StreamReader defaults to a 64 KiB read limit per readline(); search results
# with full verbatim drawer content easily exceeded that and crashed the
# proxy with asyncio.LimitOverrunError. v0.3 raises the limit to 10 MiB by
# default (env-tunable via MEMPALACE_STDOUT_LINE_LIMIT) and explicitly
# handles the error if it ever does fire.


def test_stdio_proxy_handles_large_response_line(tmp_path):
    """A subprocess that emits a single response line >64 KiB should round-trip
    cleanly. Default asyncio StreamReader limit is 64 KiB; v0.3 raises it to
    10 MiB. Without the v0.3 fix this would raise asyncio.LimitOverrunError."""
    big_script = tmp_path / "big_response_server.py"
    big_script.write_text(textwrap.dedent("""
        import json, sys
        # Emit a payload comfortably larger than asyncio's default 64 KiB
        # readline limit, but well under the 10 MiB v0.3 default. 200 KiB
        # chosen so the test runs fast but exercises the >64 KiB path.
        BIG_PAYLOAD = "x" * (200 * 1024)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            resp = {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "result": {"echoed": req.get("method", ""), "big": BIG_PAYLOAD},
            }
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
    """))

    async def run():
        proxy = http_server.StdioProxy(cmd=[sys.executable, "-u", str(big_script)])
        await proxy.start()
        try:
            resp = await proxy.request(
                {"jsonrpc": "2.0", "id": "big-1", "method": "tools/list"}
            )
            assert resp["id"] == "big-1"
            assert resp["result"]["echoed"] == "tools/list"
            # The large field round-tripped intact.
            assert len(resp["result"]["big"]) == 200 * 1024
            assert resp["result"]["big"] == "x" * (200 * 1024)
        finally:
            await proxy.stop()

    asyncio.run(run())


def test_stdio_proxy_subprocess_uses_v3_line_limit(tmp_path):
    """Verify the subprocess is actually spawned with the larger limit, not
    the asyncio default. Reads STDOUT_LINE_LIMIT from the module so an
    operator who tunes MEMPALACE_STDOUT_LINE_LIMIT down to a tiny value
    (e.g. for testing or memory-bound deploys) gets the configured limit."""
    # The default in v0.3 is 10 MiB.
    assert http_server.STDOUT_LINE_LIMIT >= 1024 * 1024, (
        "STDOUT_LINE_LIMIT default should be at least 1 MiB to handle "
        "realistic search payloads"
    )
    # Sanity: it's an int, not a string from the env var.
    assert isinstance(http_server.STDOUT_LINE_LIMIT, int)
