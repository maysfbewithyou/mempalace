"""Atrium auth middleware - validates browser-session operator identity.

Production (post-B1):
  CF Access at the edge sets `Cf-Access-Authenticated-User-Email` for every
  request that reaches our origin. Atrium accepts the request if the email
  is in the operator allow-list. CF Access also sets a JWT in
  `Cf-Access-Jwt-Assertion`; production should verify its signature against
  Cloudflare's JWKS (TODO).

Dev (B1 not yet done):
  If env var ATRIUM_DEV_BYPASS_TOKEN is set AND the request carries
  `X-Atrium-Dev-Token: <that token>`, accept as matt@interactep.com. This is
  gated behind the env var existing - production deploys don't set it.

Operator allow-list comes from ATRIUM_OPERATOR_EMAILS env var (comma-separated).
Defaults to matt@interactep.com,luke@interactep.com.

Atrium routes are gated. Non-Atrium routes (/mcp, /health, /oauth/*, etc.)
remain governed by the existing BearerAuthMiddleware in http_server.py - this
middleware ONLY inspects requests whose path starts with one of ATRIUM_PATH_PREFIXES.
"""
from __future__ import annotations

import os
import secrets
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


ATRIUM_PATH_PREFIXES = (
    "/atrium",        # All Atrium routes namespaced under /atrium/* to keep
                      # them isolated from /mcp and /health.
)


def _operator_emails() -> set:
    raw = os.environ.get(
        "ATRIUM_OPERATOR_EMAILS",
        "matt@interactep.com,luke@interactep.com",
    )
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _is_atrium_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") or path == p for p in ATRIUM_PATH_PREFIXES)


def resolve_operator(request: Request) -> str | None:
    """Return the operator email if the request is authorized, else None.

    Order:
      1. Dev bypass header (gated by ATRIUM_DEV_BYPASS_TOKEN env)
      2. CF Access header (production)
    """
    dev_token = os.environ.get("ATRIUM_DEV_BYPASS_TOKEN")
    if dev_token:
        presented = request.headers.get("X-Atrium-Dev-Token", "")
        if presented and secrets.compare_digest(presented, dev_token):
            return "matt@interactep.com"

    cf_email = request.headers.get("Cf-Access-Authenticated-User-Email", "").strip().lower()
    if cf_email and cf_email in _operator_emails():
        return cf_email

    return None


class AtriumAuthMiddleware(BaseHTTPMiddleware):
    """Gate /atrium/* paths on operator identity. Pass everything else through.

    Sets request.state.operator_email when the request is an authorized
    Atrium request. Atrium handlers read it via request.state.operator_email.
    """

    async def dispatch(self, request: Request, call_next):
        if not _is_atrium_path(request.url.path):
            # Not an Atrium route - let the regular BearerAuthMiddleware
            # (or the unauthenticated /health etc.) handle it.
            return await call_next(request)

        operator = resolve_operator(request)
        if operator is None:
            # Browser request: 302 to a "you need to authenticate" page.
            # API/HTMX request: 401 JSON.
            wants_html = "text/html" in request.headers.get("Accept", "")
            if wants_html:
                return Response(
                    "<!doctype html><html><body style='font-family:system-ui;padding:2rem;background:#0d1117;color:#e6edf3'>"
                    "<h1>Atrium - Authentication required</h1>"
                    "<p>Atrium is gated by Cloudflare Access. If you reached this page directly without an OTP challenge,"
                    " the CF Access policy isn't yet in front of <code>claude-brain.tstly.dev</code>.</p>"
                    "<p>For dev sandbox testing, set <code>ATRIUM_DEV_BYPASS_TOKEN</code> in env and pass"
                    " <code>X-Atrium-Dev-Token</code> on requests.</p>"
                    "</body></html>",
                    status_code=401,
                    media_type="text/html",
                )
            return JSONResponse(
                {
                    "error_code": "missing_atrium_auth",
                    "message": "No operator session - CF Access edge enforcement (or dev bypass token) required",
                },
                status_code=401,
            )

        request.state.operator_email = operator
        return await call_next(request)
