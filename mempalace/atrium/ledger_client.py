"""Atrium -> Atlas Agent Ledger HTTP client (Track C1, atrium v0.1.0.2).

Talks to atlas's /api/auth/exchange and /api/agent-ledger/* endpoints.
Per Schema v0.1.2 §5.1, the lifecycle is:
  1. On first call in a session, exchange bootstrap token + operator email
     for a per-operator session token.
  2. Cache the session token in process memory keyed by operator_email.
  3. Use the session token for all /api/agent-ledger/* calls.
  4. On 401, re-exchange.

Bootstrap token storage:
  - Production: env var ATLAS_BOOTSTRAP_TOKEN (post-B1, swap to whatever
    secret-management Atlas adopts).
  - Dev sandbox: env var ATLAS_DEV_BYPASS_TOKEN; we exchange this directly
    for a session token via the dev-bypass path on /api/auth/exchange.

Atlas base URL:
  - Env var ATLAS_LEDGER_BASE_URL.
  - Defaults to https://atlas-dev.tstly.dev for the dev sandbox; production
    points at the real atlas hostname when atlas itself goes behind a
    public domain.

Failure modes (PRD §4.3):
  - Atlas API unreachable -> raise LedgerUnreachable; route handlers render
    the "ledger unavailable" banner and continue with palace-only data.
  - 401/403 -> raise LedgerAuthError; route handlers render an auth banner
    and block writes.
  - Slow (>5s) -> raise LedgerTimeout; route handlers fall back to last-cached.

This module uses the stdlib `urllib` to avoid pulling in `requests` or `httpx`
as new deps. mempalace-fork already has `urllib3` transitively but not the
high-level libs.
"""
from __future__ import annotations

import json
import logging
import os
import time
import threading
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Any

logger = logging.getLogger("atrium.ledger_client")


class LedgerError(Exception):
    """Base class for ledger client errors."""


class LedgerUnreachable(LedgerError):
    """Network-level failure - DNS, refused, timeout."""


class LedgerAuthError(LedgerError):
    """401 / 403 from atlas. The token was rejected."""


class LedgerTimeout(LedgerError):
    """Atlas responded too slowly."""


class LedgerValidationError(LedgerError):
    """400 / 409 from atlas. Request shape was wrong."""


# In-process per-operator session token cache.
# {operator_email: (session_token, expires_at_unix)}
_session_cache: dict[str, tuple[str, float]] = {}
_cache_lock = threading.Lock()


def _base_url() -> str:
    return os.environ.get("ATLAS_LEDGER_BASE_URL", "https://atlas-dev.tstly.dev").rstrip("/")


def _request_timeout() -> float:
    return float(os.environ.get("ATLAS_LEDGER_TIMEOUT_SECONDS", "5"))


def _bootstrap_token() -> str:
    """The token Atrium uses to authenticate to /api/auth/exchange.

    Production: should be a long-lived service token (post-B1).
    Dev: same as ATLAS_DEV_BYPASS_TOKEN we set on the atlas Coolify deploy.
    """
    token = os.environ.get("ATLAS_BOOTSTRAP_TOKEN") or os.environ.get("ATLAS_DEV_BYPASS_TOKEN")
    if not token:
        raise LedgerError(
            "neither ATLAS_BOOTSTRAP_TOKEN nor ATLAS_DEV_BYPASS_TOKEN env var is set; "
            "Atrium cannot exchange for a ledger session token"
        )
    return token


def _do_request(method: str, path: str,
                headers: Optional[dict] = None,
                body: Optional[dict] = None,
                params: Optional[dict] = None) -> dict | list:
    """Low-level HTTP call. Returns parsed JSON; raises typed exceptions."""
    url = _base_url() + path
    if params:
        # Filter out None values; encode the rest
        params = {k: v for k, v in params.items() if v is not None}
        if params:
            url += "?" + urllib.parse.urlencode(params)

    data_bytes = None
    req_headers = {"Accept": "application/json"}
    if body is not None:
        data_bytes = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=_request_timeout()) as resp:
            text = resp.read().decode("utf-8") if resp.length != 0 else ""
            if not text:
                return {}
            return json.loads(text)
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error_code": "unknown", "message": str(e)}
        if e.code in (401, 403):
            raise LedgerAuthError(f"{e.code} {err_body.get('error_code')}: {err_body.get('message')}")
        if e.code in (400, 409):
            raise LedgerValidationError(f"{e.code} {err_body.get('error_code')}: {err_body.get('message')}")
        raise LedgerError(f"HTTP {e.code}: {err_body.get('message', str(e))}")
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError) or "timed out" in str(e.reason).lower():
            raise LedgerTimeout(f"Timeout calling {url}: {e.reason}")
        raise LedgerUnreachable(f"Cannot reach {url}: {e.reason}")
    except TimeoutError as e:
        raise LedgerTimeout(f"Timeout calling {url}: {e}")


# ===== Token exchange =====

def get_session_token(operator_email: str, surface_scope: str = "global",
                      force_refresh: bool = False) -> str:
    """Get a cached or freshly-minted session token for this operator.

    Cache key: operator_email + surface_scope. Tokens expire after 24h
    (matching Schema §5.1); we re-mint at 23h to avoid edge-case races.
    """
    cache_key = f"{operator_email}:{surface_scope}"
    now = time.time()

    if not force_refresh:
        with _cache_lock:
            cached = _session_cache.get(cache_key)
            if cached:
                token, exp = cached
                if exp - now > 60:  # at least 1 min remaining
                    return token

    # Mint a fresh token via /api/auth/exchange
    bootstrap = _bootstrap_token()
    try:
        resp = _do_request(
            "POST",
            "/api/auth/exchange",
            headers={"Authorization": f"Bearer {bootstrap}"},
            body={"surface_scope": surface_scope},
        )
    except LedgerError:
        # Surface the error so callers can render a banner
        raise

    session_token = resp.get("session_token")
    if not session_token:
        raise LedgerError(f"/api/auth/exchange did not return session_token: {resp}")

    expires_in = resp.get("expires_in", 23 * 3600)
    expires_at = now + min(expires_in, 23 * 3600)

    with _cache_lock:
        _session_cache[cache_key] = (session_token, expires_at)

    logger.info("minted session token for %s (scope=%s, auth_mode=%s)",
                operator_email, surface_scope, resp.get("auth_mode"))
    return session_token


def _ledger_call(method: str, path: str, operator_email: str,
                 body: Optional[dict] = None,
                 params: Optional[dict] = None,
                 surface_scope: str = "global") -> dict | list:
    """Make an authenticated /api/agent-ledger/* call; auto-retry once on 401."""
    token = get_session_token(operator_email, surface_scope)
    try:
        return _do_request(method, path, headers={"Authorization": f"Bearer {token}"},
                          body=body, params=params)
    except LedgerAuthError:
        # Token may have expired between cache check and request; refresh once
        token = get_session_token(operator_email, surface_scope, force_refresh=True)
        return _do_request(method, path, headers={"Authorization": f"Bearer {token}"},
                          body=body, params=params)


# ===== Convenience wrappers =====

def list_runs(operator_email: str, **params) -> list:
    return _ledger_call("GET", "/api/agent-ledger/runs", operator_email, params=params)


def get_run(operator_email: str, run_id: str) -> dict:
    return _ledger_call("GET", f"/api/agent-ledger/runs/{run_id}", operator_email)


def list_suggestions(operator_email: str, **params) -> list:
    return _ledger_call("GET", "/api/agent-ledger/suggestions", operator_email, params=params)


def get_suggestion(operator_email: str, suggestion_id: str) -> dict:
    return _ledger_call("GET", f"/api/agent-ledger/suggestions/{suggestion_id}", operator_email)


def resolve_suggestion(operator_email: str, suggestion_id: str,
                       state: str, note: Optional[str] = None) -> dict:
    body = {"state": state}
    if note is not None:
        body["note"] = note
    return _ledger_call("POST", f"/api/agent-ledger/suggestions/{suggestion_id}/resolve",
                       operator_email, body=body)


def create_review(operator_email: str, **body) -> dict:
    return _ledger_call("POST", "/api/agent-ledger/reviews", operator_email, body=body)


def list_reviews(operator_email: str, **params) -> list:
    return _ledger_call("GET", "/api/agent-ledger/reviews", operator_email, params=params)


def list_personas(operator_email: str, **params) -> list:
    return _ledger_call("GET", "/api/agent-ledger/personas", operator_email, params=params)


def upsert_persona(operator_email: str, **body) -> dict:
    return _ledger_call("POST", "/api/agent-ledger/personas", operator_email, body=body)


def patch_persona(operator_email: str, agent_name: str, **body) -> dict:
    return _ledger_call("PATCH", f"/api/agent-ledger/personas/{agent_name}",
                       operator_email, body=body)
