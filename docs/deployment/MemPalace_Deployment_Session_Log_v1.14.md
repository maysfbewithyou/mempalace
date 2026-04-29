# MemPalace Deployment — Session Log v1.14

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Status: **Phase 10 COMPLETE — claude.ai custom connector live, OAuth verified end-to-end**

> Earlier session-log snapshots: v1.0–v1.13.

---

## v1.14 — Phase 10 OAuth wrapper complete (2026-04-27)

### What's live

- Connector name: **MemPalace** (CUSTOM) at https://claude.ai/settings/connectors
- Connector URL: `https://claude-brain.tstly.dev/mcp`
- Connector status: **Configure** (same state as Matt's working voice-test precedent)
- Auth: **OAuth 2.1 authorization_code grant with PKCE (S256)** — what Anthropic's connector backend actually uses
- Secondary auth: **static MEMPALACE_BEARER_TOKEN** retained for laptop CLI diagnostics
- Token format: HS256 JWT, default 1-hour TTL
- Available across all Anthropic clients: claude.ai web + mobile (text mode) + Cowork + Claude Desktop. Voice mode still unreachable (runtime constraint, not auth).

### OAuth endpoints implemented (mempalace/oauth.py)

| Endpoint | RFC | Purpose |
|---|---|---|
| `GET /authorize` | 6749 §4.1.1 + 7636 PKCE | Validates client_id + redirect_uri, mints one-time code (10-min TTL, single-use), redirects with `?code=…&state=…`. No user-consent UI (single-user personal server). |
| `POST /oauth/token` | 6749 §4.1.3 + §4.4 | Handles **both** `authorization_code` (Anthropic) and `client_credentials` (legacy/diagnostic). Verifies client_secret + PKCE verifier (sha256 → base64url). Issues HS256 JWT. |
| `GET /.well-known/oauth-authorization-server` | 8414 | AS metadata. Advertises both grant types, S256 code_challenge_method, response_types `code`. |
| `GET /.well-known/oauth-protected-resource` | 9728 | Resource metadata. Tells clients which AS to use for /mcp. Pointed at by 401 `WWW-Authenticate: Bearer resource_metadata=…`. |

### Iteration cycles encountered

| # | Issue | Cause | Fix |
|---|---|---|---|
| 1 | `/oauth/token` returned 400 "Cannot parse form body" | Starlette's `request.form()` requires `python-multipart` even for urlencoded bodies | Parse urlencoded body manually with `urllib.parse.parse_qs`. No new dep. |
| 2 | Click "Connect" → 401 unauthorized at `/authorize` | We had only `client_credentials`; Anthropic's connector backend uses `authorization_code` with PKCE (S256). The Connector "OAuth Client ID/Secret" UI fields are for the auth_code flow's *client* authentication, not for client_credentials grant. | Add full `/authorize` endpoint + extend `/oauth/token` to handle `grant_type=authorization_code` with PKCE verification. |
| 3 (cosmetic, not yet fixed) | `WWW-Authenticate` header on /mcp 401 reports `http://...` not `https://...` | Cloudflare tunnel terminates TLS and forwards as HTTP to origin; `request.url.scheme` is `http` | Will use `MEMPALACE_OAUTH_ISSUER` env var (which is https) instead of request.url.scheme in a follow-up commit. Doesn't block the working flow. |

### Verification — final round-trip (PowerShell smoke):

```
1. AS metadata               → 200 (advertises authorization_code + client_credentials)
2. Resource metadata         → 200
3. /mcp no auth              → 401 with WWW-Authenticate
4. /authorize HEAD probe     → 302 → claude.ai/api/mcp/auth_callback?code=…&state=test
5. /oauth/token client_creds → 200 + JWT
6. /mcp with OAuth JWT       → 200, 19 mempalace_* tools
7. /mcp with tampered JWT    → 401 (correctly rejected)
8. /mcp with static bearer   → 200, 19 tools (fallback path works)
```

End-to-end Anthropic connection: **MemPalace shows "Configure" in Settings → Connectors** (same state as voice-test which Matt's parallel test confirmed works in text mode).

### Commits shipped during Phase 10

1. `2d711e6` — feat: Phase 10 OAuth 2.1 client_credentials provider for Anthropic Connectors (initial — wrong grant type, didn't work)
2. `adea9b9` — fix: parse urlencoded form body manually to avoid python-multipart dep
3. `acee4e7` — feat: add authorization_code+PKCE OAuth flow for Anthropic Connectors

### Files created / modified

| File | Status | Notes |
|---|---|---|
| `mempalace/oauth.py` | NEW | ~360 lines. Full OAuth 2.1 provider: /authorize, /oauth/token (both grant types), AS+RS metadata, JWT issue/verify, PKCE S256, in-memory authz code store |
| `mempalace/http_server.py` | MODIFIED | Middleware now accepts EITHER static bearer OR OAuth JWT. Public-paths list grew to include `/authorize`, `/oauth/token`, both `.well-known/...` paths. WWW-Authenticate header added to 401s pointing at resource metadata. |
| `pyproject.toml` | MODIFIED | Added `pyjwt>=2.8,<3` to `[http]` extra |
| `docker-compose.coolify.yml` | MODIFIED | Three new env-var declarations: MEMPALACE_OAUTH_CLIENT_ID, _CLIENT_SECRET, _JWT_SECRET |
| `tests/test_oauth.py` | NEW | 14 tests: token endpoint happy/sad paths, both grant types, metadata shape, JWT round-trip, env-var validation |
| `tests/test_http_server.py` | MODIFIED | Added test_mcp_accepts_oauth_jwt + test_mcp_emits_www_authenticate_on_unauth |

### New env vars (set in Coolify Production Environment Variables)

| Name | Length | Purpose |
|---|---|---|
| `MEMPALACE_OAUTH_CLIENT_ID` | 32 chars | Identifier for Anthropic's connector backend |
| `MEMPALACE_OAUTH_CLIENT_SECRET` | 44 chars | Validates Anthropic's identity at token endpoint |
| `MEMPALACE_OAUTH_JWT_SECRET` | 64 chars | HS256 signing key (server-side only) |

Generated locally and saved (read+write owner) at `C:\Users\phatt\.mempalace_client\oauth.json`.

### Implications for locked decisions

| Decision | Status |
|---|---|
| **D2 — bearer-first, OAuth deferred** | UPDATED: OAuth is now the primary auth for Anthropic clients (claude.ai web, mobile text, Cowork, Desktop). Static bearer kept as a SECONDARY laptop-CLI diagnostic path. Single-source-of-truth still hosted at Coolify (D1). |
| **ISSUE-5 — voice mode tool support** | Already RESOLVED with negative confirmation (per voice-test-mcp findings). OAuth lands the connector to claude.ai but voice still cannot reach custom connectors due to runtime constraint, not auth. |

### Known issues / cleanup items carried forward

- **WWW-Authenticate http→https cosmetic** — hardcode the issuer URL instead of `request.url.scheme`. Follow-up commit. Non-blocking.
- **Token rotation procedure** — file-based local copy currently has 0o600 (Modify) perms; rotation works smoothly. Periodic rotation (every 90 days or on suspicion) recommended.
- **In-memory authz code store** — single-process design; if we ever multi-replica or restart-during-flow, an in-flight authz code is lost. Not a real issue at our scale; document as a known limitation.
- **Phase 11** — Slack mining still parked.
- **Phase 9 closeout** — `MemPalace_*.md` files (now 14 of them) accumulating; will be moved to `docs/deployment/` and committed in Phase 9.

### What's next (Phase 3+ proper, now unblocked)

With Phase 10 complete, the deployment can move into actual *use* of the palace:

1. **Phase 3 (already mostly done)** — bootstrap state verified earlier; identity.txt written; four wings will populate as content gets filed.
2. **Phase 4** — mine selected Claude Projects/ subdirs into the hosted palace (the mining will hit /mcp via OAuth-issued JWT — no new infrastructure needed).
3. **Phase 5** — mine atlas codebase.
4. **Phase 6** — mine Claude.ai export (already on disk in uploads).
5. **Phase 7** — install Claude Code, register connector via `claude mcp add` with the same /mcp URL (probably will discover OAuth metadata and walk the same flow as claude.ai web).
6. **Phase 8** — wire hooks + scheduled review tasks.
7. **Phase 9** — closeout: docs commit, tag, branch cleanup.

The hardest infrastructure work is now behind us. The remaining phases are mostly content + configuration.

### Versioning policy

Every artifact carries a version stamp. Decision and design locks bump session-log minor version. Each prior session-log version preserved as a rollback anchor.
