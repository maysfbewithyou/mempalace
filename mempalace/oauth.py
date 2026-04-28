"""OAuth 2.0 / 2.1 client_credentials provider for the MemPalace HTTP wrapper.

version: 0.1
phase: 10

Implements the minimum endpoints needed for Anthropic Connectors (Cowork,
claude.ai web, Claude Desktop, mobile text mode) to authenticate with our
MCP server:

  POST  /oauth/token                              — RFC 6749 token endpoint
  GET   /.well-known/oauth-authorization-server   — RFC 8414 AS metadata
  GET   /.well-known/oauth-protected-resource     — RFC 9728 resource metadata

JWTs are HS256 with a server-side secret; self-contained (no DB lookup
required for verification). Default TTL 1 hour.

Anthropic's flow:
  1. User adds custom connector at claude.ai with URL=https://claude-brain.tstly.dev/mcp
     plus OAuth Client ID + Client Secret in Advanced settings.
  2. Anthropic's connector backend POSTs to /oauth/token with:
       grant_type=client_credentials, client_id=..., client_secret=...
     Either via HTTP Basic auth header or form-body params.
  3. We validate creds (constant-time compare), return:
       { access_token: <jwt>, token_type: "Bearer", expires_in: 3600, scope: "mcp" }
  4. Anthropic uses the JWT for subsequent /mcp calls:
       Authorization: Bearer <jwt>

The MEMPALACE_BEARER_TOKEN static-bearer auth path remains as a SECONDARY
mechanism for laptop CLI diagnostics — see http_server.BearerAuthMiddleware.

Env vars (all required at runtime):
  MEMPALACE_OAUTH_CLIENT_ID       — >=16 chars, used by Anthropic to identify itself
  MEMPALACE_OAUTH_CLIENT_SECRET   — >=16 chars, OAuth secret
  MEMPALACE_OAUTH_JWT_SECRET      — >=32 chars, HS256 signing key
  MEMPALACE_OAUTH_ISSUER          — optional; defaults to https://claude-brain.tstly.dev
  MEMPALACE_OAUTH_TOKEN_TTL       — optional; defaults to 3600 (seconds)
"""

from __future__ import annotations

import base64
import os
import secrets
import time
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# ── Configuration (env-var driven, fail-fast on misconfig) ────────────────────

def _get_oauth_client_id() -> str:
    v = os.environ.get("MEMPALACE_OAUTH_CLIENT_ID")
    if not v or len(v) < 16:
        raise RuntimeError(
            "MEMPALACE_OAUTH_CLIENT_ID env var is required and must be >=16 chars. "
            "Generate via: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
    return v


def _get_oauth_client_secret() -> str:
    v = os.environ.get("MEMPALACE_OAUTH_CLIENT_SECRET")
    if not v or len(v) < 16:
        raise RuntimeError(
            "MEMPALACE_OAUTH_CLIENT_SECRET env var is required and must be >=16 chars."
        )
    return v


def _get_jwt_secret() -> str:
    v = os.environ.get("MEMPALACE_OAUTH_JWT_SECRET")
    if not v or len(v) < 32:
        raise RuntimeError(
            "MEMPALACE_OAUTH_JWT_SECRET env var is required and must be >=32 chars."
        )
    return v


def _get_issuer() -> str:
    return os.environ.get(
        "MEMPALACE_OAUTH_ISSUER",
        "https://claude-brain.tstly.dev",
    )


JWT_AUDIENCE = "mempalace-mcp"
JWT_ALGORITHM = "HS256"


def _get_token_ttl() -> int:
    try:
        return int(os.environ.get("MEMPALACE_OAUTH_TOKEN_TTL", "3600"))
    except ValueError:
        return 3600


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_basic_auth(header_value: str) -> tuple[Optional[str], Optional[str]]:
    """Decode an HTTP Basic auth header into (user, password). Returns (None, None) on failure."""
    if not header_value or not header_value.lower().startswith("basic "):
        return None, None
    try:
        decoded = base64.b64decode(header_value[6:]).decode("utf-8")
        user, sep, pwd = decoded.partition(":")
        if not sep:
            return None, None
        return user, pwd
    except Exception:
        return None, None


# ── JWT issuance / verification ──────────────────────────────────────────────

def issue_jwt(client_id: str) -> tuple[str, int]:
    """Issue a signed access token for the given client.

    Returns (jwt_string, ttl_seconds). The JWT carries iss, sub, aud, iat, exp, scope.
    """
    import jwt  # lazy import so the module loads without pyjwt installed

    ttl = _get_token_ttl()
    now = int(time.time())
    payload = {
        "iss": _get_issuer(),
        "sub": client_id,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + ttl,
        "scope": "mcp",
    }
    token = jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)
    # PyJWT >= 2 returns str; <2 returned bytes. Normalize to str.
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token, ttl


def verify_jwt(token: str) -> bool:
    """Verify an OAuth-issued JWT. Returns True iff signature valid AND not expired
    AND issuer/audience match.
    """
    import jwt

    try:
        jwt.decode(
            token,
            _get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=_get_issuer(),
        )
        return True
    except jwt.InvalidTokenError:
        return False
    except Exception:
        # Defensive — never let a token-verification path raise into the request handler.
        return False


# ── Endpoint handlers ─────────────────────────────────────────────────────────

async def token_endpoint(request: Request) -> Response:
    """OAuth 2.0 token endpoint, client_credentials grant only.

    Accepts client credentials via either:
      - Authorization: Basic base64(client_id:client_secret)   (RFC 6749 §2.3.1)
      - POST body params: client_id=..., client_secret=...     (client_secret_post)
    """
    try:
        form = await request.form()
    except Exception:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Cannot parse form body"},
            status_code=400,
        )

    grant_type = form.get("grant_type", "")
    if grant_type != "client_credentials":
        return JSONResponse(
            {
                "error": "unsupported_grant_type",
                "error_description": "Only client_credentials is supported",
            },
            status_code=400,
        )

    auth_header = request.headers.get("authorization", "")
    basic_user, basic_pwd = _decode_basic_auth(auth_header)
    client_id = basic_user or form.get("client_id", "") or ""
    client_secret = basic_pwd or form.get("client_secret", "") or ""

    if not client_id or not client_secret:
        return JSONResponse(
            {
                "error": "invalid_request",
                "error_description": "client_id and client_secret are required",
            },
            status_code=400,
        )

    expected_id = _get_oauth_client_id()
    expected_secret = _get_oauth_client_secret()

    id_ok = secrets.compare_digest(client_id.encode("utf-8"), expected_id.encode("utf-8"))
    secret_ok = secrets.compare_digest(client_secret.encode("utf-8"), expected_secret.encode("utf-8"))

    if not (id_ok and secret_ok):
        return JSONResponse(
            {
                "error": "invalid_client",
                "error_description": "Client authentication failed",
            },
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="MemPalace"'},
        )

    token, ttl = issue_jwt(client_id)
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "scope": "mcp",
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def authorization_server_metadata(request: Request) -> Response:
    """RFC 8414 OAuth 2.0 Authorization Server Metadata.

    Anthropic's connector backend reads this to discover where to fetch tokens.
    """
    issuer = _get_issuer()
    return JSONResponse({
        "issuer": issuer,
        "token_endpoint": f"{issuer}/oauth/token",
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "grant_types_supported": ["client_credentials"],
        "response_types_supported": ["token"],
        "scopes_supported": ["mcp"],
        "service_documentation": "https://github.com/maysfbewithyou/mempalace",
    })


async def protected_resource_metadata(request: Request) -> Response:
    """RFC 9728 OAuth 2.0 Protected Resource Metadata.

    Tells MCP clients which authorization server protects this resource. Referenced
    from the WWW-Authenticate header on 401s from /mcp.
    """
    issuer = _get_issuer()
    return JSONResponse({
        "resource": f"{issuer}/mcp",
        "authorization_servers": [issuer],
        "scopes_supported": ["mcp"],
        "bearer_methods_supported": ["header"],
    })
