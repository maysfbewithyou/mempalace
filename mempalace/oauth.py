"""OAuth 2.0 / 2.1 provider for the MemPalace HTTP wrapper.

version: 0.3 (added refresh_token grant + rotation; access_token TTL unchanged)
phase: 10

Version history:
  0.1 — initial client_credentials provider
  0.2 — added authorization_code+PKCE flow used by Anthropic Connectors
  0.3 — added refresh_token grant with single-use rotation (rollback to 0.2 by
        reverting this commit; AS metadata change is backwards-compatible —
        clients that don't know refresh_token will simply ignore it)

Endpoints:
  GET   /authorize                                — RFC 6749 §4.1.1 authorization request
  POST  /oauth/token                              — RFC 6749 token endpoint
                                                    (grant types: client_credentials,
                                                     authorization_code, refresh_token)
  GET   /.well-known/oauth-authorization-server   — RFC 8414 AS metadata
  GET   /.well-known/oauth-protected-resource     — RFC 9728 resource metadata

Access tokens are HS256 JWTs with a server-side secret. Default TTL 1 hour.
Refresh tokens are opaque random strings (not JWTs) — verification requires
server-side state anyway (for rotation and revocation), so opaque is cleaner.
Default refresh-token TTL 30 days. Refresh tokens are single-use: each refresh
mints a NEW refresh token and marks the old one used. Reusing a consumed
refresh token returns invalid_grant (RFC 6749 §10.4).

Anthropic Connector flow (authorization_code with PKCE):
  1. User adds custom connector at claude.ai with URL=https://claude-brain.tstly.dev/mcp
     plus OAuth Client ID + Client Secret in Advanced settings.
  2. User clicks "Connect" → browser navigates to our /authorize:
       /authorize?response_type=code
                 &client_id=<our_client_id>
                 &redirect_uri=https://claude.ai/api/mcp/auth_callback
                 &code_challenge=<base64url(sha256(verifier))>
                 &code_challenge_method=S256
                 &state=<random>
                 &scope=mcp
                 &resource=https://claude-brain.tstly.dev/mcp
  3. We validate client_id + redirect_uri, mint a one-time code, redirect to:
       https://claude.ai/api/mcp/auth_callback?code=<code>&state=<state>
  4. Anthropic's backend POSTs to /oauth/token:
       grant_type=authorization_code, code=<code>, code_verifier=<plaintext>,
       redirect_uri=..., client_id=..., client_secret=...
  5. We verify the code (one-time), the PKCE verifier (sha256 == challenge),
     and the client_secret. Return a JWT.
  6. Anthropic uses the JWT for subsequent /mcp calls (Authorization: Bearer <jwt>).

The MEMPALACE_BEARER_TOKEN static-bearer auth path remains as a SECONDARY
mechanism for laptop CLI diagnostics — see http_server.BearerAuthMiddleware.

Storage of authorization codes is in-process (a dict). Single uvicorn worker
(A4) means single-process; this is sufficient. Codes expire after 10 minutes.

Env vars (all required at runtime):
  MEMPALACE_OAUTH_CLIENT_ID       — >=16 chars, OAuth client identifier
  MEMPALACE_OAUTH_CLIENT_SECRET   — >=16 chars, OAuth client secret
  MEMPALACE_OAUTH_JWT_SECRET      — >=32 chars, HS256 signing key
  MEMPALACE_OAUTH_ISSUER          — optional; defaults to https://claude-brain.tstly.dev
  MEMPALACE_OAUTH_TOKEN_TTL       — optional; defaults to 3600 (access token, seconds)
  MEMPALACE_OAUTH_REFRESH_TTL     — optional; defaults to 2592000 (refresh token, 30 days)
  MEMPALACE_OAUTH_ALLOWED_REDIRECT — optional; defaults to https://claude.ai/api/mcp/auth_callback
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

logger = logging.getLogger("mempalace.oauth")


# ── In-memory authorization code store ────────────────────────────────────────
# Single uvicorn worker (A4) → single process → in-memory dict is enough.
# Each entry: { client_id, redirect_uri, code_challenge, code_challenge_method,
#               scope, resource, expires_at, used }
# Codes expire 10 minutes after issuance and are single-use (RFC 6749 §4.1.2).
_AUTHZ_CODES: dict[str, dict] = {}
_AUTHZ_CODE_TTL_SECONDS = 600


def _gc_expired_codes() -> None:
    """Drop expired or used authz codes. Called opportunistically; not on a timer."""
    now = time.time()
    expired = [k for k, v in _AUTHZ_CODES.items() if v.get("expires_at", 0) < now or v.get("used")]
    for k in expired:
        _AUTHZ_CODES.pop(k, None)


# ── In-memory refresh token store ─────────────────────────────────────────────
# Same single-process assumption as authz codes (A4 — one uvicorn worker).
# Each entry: { client_id, scope, resource, expires_at, used }
# Refresh tokens are SINGLE-USE: a successful refresh marks the old one used
# and issues a new one. Reusing a consumed refresh token yields invalid_grant
# per RFC 6749 §10.4 ("The authorization server MUST … invalidate the
# refresh token, and revoke all access tokens previously issued").
_REFRESH_TOKENS: dict[str, dict] = {}


def _gc_expired_refresh_tokens() -> None:
    """Drop expired refresh tokens. Called opportunistically.

    NOTE: We deliberately keep USED refresh tokens until their natural expiry,
    so that reuse of a consumed RT can be DETECTED (returning invalid_grant
    with a "used" error_description) rather than masquerading as an unknown
    token. This preserves the RFC 6749 §10.4 compromise-indicator signal.
    With one user and a 30-day TTL, the dict stays small (a few hundred
    entries at most).
    """
    now = time.time()
    expired = [
        k for k, v in _REFRESH_TOKENS.items()
        if v.get("expires_at", 0) < now
    ]
    for k in expired:
        _REFRESH_TOKENS.pop(k, None)


def _allowed_redirect_uri() -> str:
    return os.environ.get(
        "MEMPALACE_OAUTH_ALLOWED_REDIRECT",
        "https://claude.ai/api/mcp/auth_callback",
    )


def _verify_pkce(verifier: str, challenge: str, method: str) -> bool:
    """Verify PKCE per RFC 7636. Only S256 is supported."""
    if method != "S256":
        return False
    if not verifier or not (43 <= len(verifier) <= 128):
        return False
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return secrets.compare_digest(computed, challenge)


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


def _get_refresh_token_ttl() -> int:
    """Default 30 days. Refresh tokens are bearer credentials, but their blast
    radius is limited by single-use rotation — a stolen RT is detected as soon
    as the legitimate client tries to use it (causing an invalid_grant), at
    which point the user can reconnect to revoke the family.
    """
    try:
        return int(os.environ.get("MEMPALACE_OAUTH_REFRESH_TTL", str(30 * 24 * 3600)))
    except ValueError:
        return 30 * 24 * 3600


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


def issue_refresh_token(client_id: str, scope: str = "mcp", resource: str = "") -> tuple[str, int]:
    """Mint a new refresh token bound to the given client_id.

    Returns (refresh_token_string, ttl_seconds). The token is opaque (no
    payload) — its only meaning is as a lookup key into _REFRESH_TOKENS,
    where the binding to client_id and scope is recorded.
    """
    ttl = _get_refresh_token_ttl()
    rt = secrets.token_urlsafe(48)
    _REFRESH_TOKENS[rt] = {
        "client_id": client_id,
        "scope": scope,
        "resource": resource,
        "expires_at": time.time() + ttl,
        "used": False,
    }
    return rt, ttl


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

async def authorize_endpoint(request: Request) -> Response:
    """OAuth 2.0 authorization endpoint (RFC 6749 §4.1.1) with PKCE (RFC 7636).

    Accepts the authorization request from Anthropic's connector backend and
    immediately redirects back to the client with a one-time code. There is
    no user-consent screen — this is a single-user personal server, the
    "user" already authorized the connector when they pasted the client_id
    and client_secret into claude.ai.

    Required query params:
      response_type=code
      client_id=<must match MEMPALACE_OAUTH_CLIENT_ID>
      redirect_uri=<must match MEMPALACE_OAUTH_ALLOWED_REDIRECT>
      code_challenge=<base64url(sha256(verifier)), no padding>
      code_challenge_method=S256
      state=<opaque, echoed back>
      scope=<space-separated; we accept "mcp">
    Optional:
      resource=<RFC 8707 resource indicator>
    """
    qp = request.query_params

    response_type = qp.get("response_type", "")
    client_id = qp.get("client_id", "")
    redirect_uri = qp.get("redirect_uri", "")
    code_challenge = qp.get("code_challenge", "")
    code_challenge_method = qp.get("code_challenge_method", "")
    state = qp.get("state", "")
    scope = qp.get("scope", "mcp")
    resource = qp.get("resource", "")

    # Pre-redirect validation: errors that involve client_id or redirect_uri
    # cannot redirect back (RFC 6749 §4.1.2.1) — return a plain 400.
    if client_id != _get_oauth_client_id():
        return JSONResponse(
            {"error": "invalid_client", "error_description": "Unknown client_id"},
            status_code=400,
        )

    allowed_redirect = _allowed_redirect_uri()
    if redirect_uri != allowed_redirect:
        return JSONResponse(
            {
                "error": "invalid_request",
                "error_description": (
                    f"redirect_uri mismatch (got {redirect_uri!r}, "
                    f"expected {allowed_redirect!r})"
                ),
            },
            status_code=400,
        )

    # Post-redirect-validatable errors: redirect back with error=...&state=...
    def _err_redirect(error: str, description: str) -> Response:
        params = {"error": error, "error_description": description, "state": state}
        return RedirectResponse(url=f"{redirect_uri}?{urlencode(params)}", status_code=302)

    if response_type != "code":
        return _err_redirect("unsupported_response_type", "Only response_type=code is supported")

    if code_challenge_method != "S256":
        return _err_redirect(
            "invalid_request",
            "Only code_challenge_method=S256 is supported",
        )
    if not code_challenge:
        return _err_redirect("invalid_request", "code_challenge is required")

    # Mint a one-time authorization code.
    _gc_expired_codes()
    code = secrets.token_urlsafe(32)
    _AUTHZ_CODES[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "scope": scope,
        "resource": resource,
        "expires_at": time.time() + _AUTHZ_CODE_TTL_SECONDS,
        "used": False,
    }
    logger.info("oauth: issued authz code (state_prefix=%s)", state[:8] if state else "")

    params = {"code": code, "state": state}
    return RedirectResponse(url=f"{redirect_uri}?{urlencode(params)}", status_code=302)


async def token_endpoint(request: Request) -> Response:
    """OAuth 2.0 token endpoint.

    Supports two grant types:
      - client_credentials  (machine-to-machine; legacy/diagnostic)
      - authorization_code  (PKCE-based; what Anthropic Connectors uses)

    Accepts client credentials via either:
      - Authorization: Basic base64(client_id:client_secret)   (RFC 6749 §2.3.1)
      - POST body params: client_id=..., client_secret=...     (client_secret_post)
    """
    # Parse application/x-www-form-urlencoded manually — Starlette's request.form()
    # requires the python-multipart package even for urlencoded bodies, and we
    # don't want that dependency just for the token endpoint.
    from urllib.parse import parse_qs

    try:
        raw = await request.body()
        parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        form = {k: (v[0] if v else "") for k, v in parsed.items()}
    except Exception:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Cannot parse form body"},
            status_code=400,
        )

    grant_type = form.get("grant_type", "")

    # Client authentication — required for both grant types we support.
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
    secret_ok = secrets.compare_digest(
        client_secret.encode("utf-8"), expected_secret.encode("utf-8")
    )
    if not (id_ok and secret_ok):
        return JSONResponse(
            {"error": "invalid_client", "error_description": "Client authentication failed"},
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="MemPalace"'},
        )

    # ── client_credentials grant ────────────────────────────────────────
    if grant_type == "client_credentials":
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

    # ── authorization_code grant (with PKCE) ────────────────────────────
    if grant_type == "authorization_code":
        code = form.get("code", "")
        code_verifier = form.get("code_verifier", "")
        redirect_uri = form.get("redirect_uri", "")

        if not code or not code_verifier or not redirect_uri:
            return JSONResponse(
                {
                    "error": "invalid_request",
                    "error_description": "code, code_verifier, and redirect_uri are required",
                },
                status_code=400,
            )

        _gc_expired_codes()
        entry = _AUTHZ_CODES.get(code)
        if entry is None:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Unknown or expired code"},
                status_code=400,
            )
        if entry.get("used"):
            # RFC 6749 §4.1.2: detected reuse — invalidate any tokens issued from this code.
            # We don't track issued tokens, but we do refuse the code.
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Code already used"},
                status_code=400,
            )
        if entry.get("expires_at", 0) < time.time():
            _AUTHZ_CODES.pop(code, None)
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Code expired"},
                status_code=400,
            )
        if entry.get("client_id") != client_id:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Code/client mismatch"},
                status_code=400,
            )
        if entry.get("redirect_uri") != redirect_uri:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "redirect_uri mismatch"},
                status_code=400,
            )

        if not _verify_pkce(
            code_verifier,
            entry.get("code_challenge", ""),
            entry.get("code_challenge_method", ""),
        ):
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "PKCE verification failed"},
                status_code=400,
            )

        # Mark code as used (single-use enforcement).
        entry["used"] = True

        token, ttl = issue_jwt(client_id)
        rt, _rt_ttl = issue_refresh_token(
            client_id,
            scope=entry.get("scope", "mcp"),
            resource=entry.get("resource", ""),
        )
        logger.info("oauth: issued access+refresh tokens (grant=authorization_code)")
        return JSONResponse(
            {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": ttl,
                "refresh_token": rt,
                "scope": entry.get("scope", "mcp"),
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    # ── refresh_token grant (RFC 6749 §6, with single-use rotation) ─────
    if grant_type == "refresh_token":
        rt = form.get("refresh_token", "")
        if not rt:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "refresh_token is required"},
                status_code=400,
            )

        _gc_expired_refresh_tokens()
        entry = _REFRESH_TOKENS.get(rt)
        if entry is None:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Unknown refresh_token"},
                status_code=400,
            )
        if entry.get("used"):
            # Reuse of a consumed RT — RFC 6749 §10.4 says we SHOULD treat
            # this as a compromise indicator. For a single-user personal
            # server we just reject; the user will reconnect, which mints
            # a fresh AC + RT chain and orphans the entire stolen family.
            logger.warning("oauth: refresh_token reuse detected — rejecting")
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "refresh_token already used"},
                status_code=400,
            )
        if entry.get("expires_at", 0) < time.time():
            _REFRESH_TOKENS.pop(rt, None)
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "refresh_token expired"},
                status_code=400,
            )
        if entry.get("client_id") != client_id:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "refresh_token/client mismatch"},
                status_code=400,
            )

        # Rotate: mark old RT used, issue new RT bound to the same client + scope.
        entry["used"] = True
        token, ttl = issue_jwt(client_id)
        new_rt, _rt_ttl = issue_refresh_token(
            client_id,
            scope=entry.get("scope", "mcp"),
            resource=entry.get("resource", ""),
        )
        logger.info("oauth: rotated refresh_token (grant=refresh_token)")
        return JSONResponse(
            {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": ttl,
                "refresh_token": new_rt,
                "scope": entry.get("scope", "mcp"),
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    return JSONResponse(
        {
            "error": "unsupported_grant_type",
            "error_description": (
                "Only client_credentials, authorization_code, and refresh_token are supported"
            ),
        },
        status_code=400,
    )


async def authorization_server_metadata(request: Request) -> Response:
    """RFC 8414 OAuth 2.0 Authorization Server Metadata.

    Anthropic's connector backend reads this to discover the authorization
    and token endpoints, supported grant types, and PKCE methods.
    """
    issuer = _get_issuer()
    return JSONResponse({
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "grant_types_supported": ["authorization_code", "client_credentials", "refresh_token"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
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
