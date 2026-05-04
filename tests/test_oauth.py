"""Tests for the OAuth 2.0 provider.

version: 0.2 (added refresh_token grant tests; rollback to 0.1 by deleting
              the "refresh_token grant" section)
phase: 10
covers: mempalace.oauth (token endpoint, metadata, JWT issue/verify,
        refresh_token issuance + rotation + reuse detection)
"""

from __future__ import annotations

import base64
import os

import pytest

pytest.importorskip("starlette")
pytest.importorskip("httpx")
pytest.importorskip("jwt")  # PyJWT

# Set required env vars BEFORE importing oauth (it reads them at call time, but
# tests should never run with stale env). Use long enough values to pass guards.
os.environ.setdefault("MEMPALACE_OAUTH_CLIENT_ID", "test-client-id-1234567890aaaa")
os.environ.setdefault("MEMPALACE_OAUTH_CLIENT_SECRET", "test-client-secret-1234567890aaaa")
os.environ.setdefault("MEMPALACE_OAUTH_JWT_SECRET", "x" * 64)
os.environ.setdefault("MEMPALACE_OAUTH_ISSUER", "https://test.example/")

from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from mempalace import oauth  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app():
    """A minimal Starlette app exposing only the OAuth endpoints — no auth middleware."""
    return Starlette(routes=[
        Route("/authorize", oauth.authorize_endpoint, methods=["GET"]),
        Route("/oauth/token", oauth.token_endpoint, methods=["POST"]),
        Route(
            "/.well-known/oauth-authorization-server",
            oauth.authorization_server_metadata,
            methods=["GET"],
        ),
        Route(
            "/.well-known/oauth-protected-resource",
            oauth.protected_resource_metadata,
            methods=["GET"],
        ),
    ])


@pytest.fixture(autouse=True)
def _clear_oauth_state():
    """Refresh tokens and authz codes live in module-level dicts. Clear between
    tests so one test's leftover RT can't affect another's reuse-detection logic.
    """
    oauth._REFRESH_TOKENS.clear()
    oauth._AUTHZ_CODES.clear()
    yield
    oauth._REFRESH_TOKENS.clear()
    oauth._AUTHZ_CODES.clear()


@pytest.fixture
def client(app):
    return TestClient(app)


VALID_CLIENT_ID = "test-client-id-1234567890aaaa"
VALID_CLIENT_SECRET = "test-client-secret-1234567890aaaa"


# ── /oauth/token — happy path (form-body credentials) ────────────────────────


def test_token_endpoint_form_body_creds_success(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["scope"] == "mcp"
    assert body["expires_in"] > 0
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 50

    # The Cache-Control / Pragma headers are required for token responses (RFC 6749 §5.1).
    assert "no-store" in r.headers.get("cache-control", "")


# ── /oauth/token — happy path (HTTP Basic auth header) ───────────────────────


def test_token_endpoint_basic_auth_success(client):
    creds = f"{VALID_CLIENT_ID}:{VALID_CLIENT_SECRET}".encode()
    basic = base64.b64encode(creds).decode()
    r = client.post(
        "/oauth/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {basic}"},
    )
    assert r.status_code == 200
    assert r.json()["token_type"] == "Bearer"


# ── /oauth/token — sad paths ──────────────────────────────────────────────────


def test_token_endpoint_wrong_grant_type(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "password",
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_grant_type"


def test_token_endpoint_missing_creds(client):
    r = client.post(
        "/oauth/token",
        data={"grant_type": "client_credentials"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


def test_token_endpoint_wrong_client_id(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "wrong-client-id-padding-padding",
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_client"


def test_token_endpoint_wrong_client_secret(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": VALID_CLIENT_ID,
            "client_secret": "wrong-secret-padding-padding-padding",
        },
    )
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_client"


# ── Metadata endpoints ────────────────────────────────────────────────────────


def test_authorization_server_metadata_shape(client):
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    assert body["issuer"] == "https://test.example/"
    assert body["token_endpoint"].endswith("/oauth/token")
    assert "client_credentials" in body["grant_types_supported"]
    assert "client_secret_basic" in body["token_endpoint_auth_methods_supported"]
    assert "client_secret_post" in body["token_endpoint_auth_methods_supported"]


def test_protected_resource_metadata_shape(client):
    r = client.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    body = r.json()
    assert body["resource"].endswith("/mcp")
    assert body["authorization_servers"] == ["https://test.example/"]
    assert "header" in body["bearer_methods_supported"]


# ── JWT issuance + verification ───────────────────────────────────────────────


def test_issue_jwt_and_verify_round_trip():
    token, ttl = oauth.issue_jwt(VALID_CLIENT_ID)
    assert isinstance(token, str)
    assert ttl == 3600
    assert oauth.verify_jwt(token) is True


def test_verify_jwt_rejects_garbage():
    assert oauth.verify_jwt("not-a-jwt") is False
    assert oauth.verify_jwt("") is False


def test_verify_jwt_rejects_tampered_signature(monkeypatch):
    token, _ = oauth.issue_jwt(VALID_CLIENT_ID)
    # Flip a few bytes in the signature segment.
    parts = token.split(".")
    assert len(parts) == 3
    tampered = parts[0] + "." + parts[1] + "." + parts[2][::-1]
    assert oauth.verify_jwt(tampered) is False


def test_verify_jwt_rejects_wrong_secret_key(monkeypatch):
    """A token signed with one secret should not verify under a different secret."""
    import jwt

    bogus = jwt.encode(
        {
            "iss": "https://test.example/",
            "sub": VALID_CLIENT_ID,
            "aud": "mempalace-mcp",
            "iat": 0,
            "exp": 9999999999,
        },
        "this-is-a-different-key-padding-padding",
        algorithm="HS256",
    )
    if isinstance(bogus, bytes):
        bogus = bogus.decode("utf-8")
    assert oauth.verify_jwt(bogus) is False


# ── Env-var validation ────────────────────────────────────────────────────────


def test_client_id_required(monkeypatch):
    monkeypatch.delenv("MEMPALACE_OAUTH_CLIENT_ID", raising=False)
    with pytest.raises(RuntimeError, match="MEMPALACE_OAUTH_CLIENT_ID"):
        oauth._get_oauth_client_id()


def test_client_secret_required(monkeypatch):
    monkeypatch.delenv("MEMPALACE_OAUTH_CLIENT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="MEMPALACE_OAUTH_CLIENT_SECRET"):
        oauth._get_oauth_client_secret()


def test_jwt_secret_required(monkeypatch):
    monkeypatch.delenv("MEMPALACE_OAUTH_JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="MEMPALACE_OAUTH_JWT_SECRET"):
        oauth._get_jwt_secret()


def test_jwt_secret_min_length(monkeypatch):
    monkeypatch.setenv("MEMPALACE_OAUTH_JWT_SECRET", "short")
    with pytest.raises(RuntimeError, match=">=32"):
        oauth._get_jwt_secret()


# ── refresh_token grant (v0.3) ────────────────────────────────────────────────
#
# These tests drive the token endpoint at the form-body level for client_creds,
# and exercise issue_refresh_token() directly to seed RT state for the refresh
# flow. We don't run the /authorize PKCE dance here — that's covered by the
# authorization_code-flow tests above and the AC integration test below.


import hashlib  # noqa: E402  — used by the AC-flow integration test


def _seed_refresh_token(client_id: str = VALID_CLIENT_ID) -> str:
    """Helper: mint a refresh token bound to client_id and return the RT string."""
    rt, _ttl = oauth.issue_refresh_token(client_id, scope="mcp")
    return rt


def test_refresh_token_grant_happy_path(client):
    rt = _seed_refresh_token()
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] > 0
    assert oauth.verify_jwt(body["access_token"]) is True
    # A new RT was issued and it's different from the one we sent.
    assert "refresh_token" in body
    assert body["refresh_token"] != rt


def test_refresh_token_rotation_invalidates_old(client):
    """After a successful refresh, the OLD refresh_token must be rejected."""
    rt = _seed_refresh_token()
    r1 = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r1.status_code == 200
    new_rt = r1.json()["refresh_token"]

    # Reusing the original RT must now fail.
    r2 = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r2.status_code == 400
    assert r2.json()["error"] == "invalid_grant"
    assert "used" in r2.json()["error_description"].lower()

    # But the NEW RT still works.
    r3 = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": new_rt,
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r3.status_code == 200


def test_refresh_token_unknown_rejected(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": "not-a-real-refresh-token",
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_refresh_token_missing_rejected(client):
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_request"


def test_refresh_token_expired_rejected(client):
    """An RT past its expires_at should be rejected and garbage-collected."""
    rt = _seed_refresh_token()
    # Force expiry by rewinding the stored expires_at.
    oauth._REFRESH_TOKENS[rt]["expires_at"] = 1.0  # Unix epoch + 1s
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"
    # GC ran and the entry is gone.
    assert rt not in oauth._REFRESH_TOKENS


def test_refresh_token_client_mismatch_rejected(client):
    """An RT presented with a different client_id must be rejected, even if
    that client_id authenticates with valid credentials."""
    # Bind the RT to a *different* (fake) client.
    rt, _ = oauth.issue_refresh_token("some-other-client-id-padding")
    r = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_metadata_advertises_refresh_token(client):
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    grants = r.json()["grant_types_supported"]
    assert "refresh_token" in grants
    assert "authorization_code" in grants
    assert "client_credentials" in grants


def test_authorization_code_flow_returns_refresh_token(client):
    """Integration: walk /authorize → /oauth/token (authorization_code) and
    confirm the response includes a refresh_token alongside the access_token.
    """
    # PKCE: pick a verifier, compute the S256 challenge.
    import base64 as _b64
    verifier = "v" * 64  # 64 chars, in [43,128] per RFC 7636
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = _b64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    redirect_uri = oauth._allowed_redirect_uri()

    # 1. /authorize → 302 redirect with ?code=...&state=...
    auth_resp = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": VALID_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz-state",
            "scope": "mcp",
        },
        follow_redirects=False,
    )
    assert auth_resp.status_code == 302
    location = auth_resp.headers["location"]
    # Pull the code out of the redirect URL.
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(location).query)
    code = qs["code"][0]
    assert qs["state"][0] == "xyz-state"

    # 2. /oauth/token with grant_type=authorization_code.
    tok_resp = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "client_id": VALID_CLIENT_ID,
            "client_secret": VALID_CLIENT_SECRET,
        },
    )
    assert tok_resp.status_code == 200, tok_resp.text
    body = tok_resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "Bearer"
    assert oauth.verify_jwt(body["access_token"]) is True


def test_issue_refresh_token_helper_round_trip():
    rt, ttl = oauth.issue_refresh_token(VALID_CLIENT_ID, scope="mcp")
    assert isinstance(rt, str) and len(rt) > 30
    assert ttl == 30 * 24 * 3600  # default 30 days
    entry = oauth._REFRESH_TOKENS[rt]
    assert entry["client_id"] == VALID_CLIENT_ID
    assert entry["scope"] == "mcp"
    assert entry["used"] is False
