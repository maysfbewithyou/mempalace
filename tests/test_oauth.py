"""Tests for the OAuth 2.0 client_credentials provider.

version: 0.1
phase: 10
covers: mempalace.oauth (token endpoint, metadata, JWT issue/verify)
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
