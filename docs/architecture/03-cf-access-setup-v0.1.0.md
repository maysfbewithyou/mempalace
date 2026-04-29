# Cloudflare Access — Setup for `claude-brain.tstly.dev` (v0.1.0)

| Field | Value |
|---|---|
| Document | Cloudflare Access Setup — `claude-brain.tstly.dev` |
| Version | v0.1.0 |
| Date | 2026-04-28 |
| Author | Claude (Cowork session, on behalf of Matt) |
| Operator | Matt (this is operational; runs at his laptop) |
| Status | Pre-ship checklist for Atrium. Mirrored from Atrium PRD v0.1.1 §3.3.1. |
| Companion | `Claude Workspace\mempalace-fork\docs\ui\02-mempalace-ui-prd-v0.1.0.md` (in-file v0.1.1) §3.3 + §3.3.1 |
| Governance | Atlas Security Admin Governance v0.1.0 §2 (trust-zone — Cloudflare edge applies Service Auth + Email OTP); secrets-convention durable-backup pattern |

---

## Why this exists

Atrium (the MemPalace UI tool, locked v0.1.1) ships at `https://claude-brain.tstly.dev/`. **Atrium MUST NOT ship** until Cloudflare Access (service-auth + email-OTP for `matt@interactep.com` / `luke@interactep.com`) is verifiably in front of that hostname.

The hostname is currently protected only by the existing Cloudflare Tunnel + the Starlette app's bearer/OAuth on `/mcp`. That's enough for an MCP endpoint behind a hard-to-guess token, but it's **not enough** for a browser-facing UI that an operator might bookmark, screen-share, or open on a laptop in a coffee shop.

This is operational work — it requires the Coolify dashboard and the Cloudflare Zero Trust dashboard. It is **not** part of the Atrium build. Matt runs it at his laptop **before** the Atrium build kicks off.

---

## Prerequisites

- Cloudflare Zero Trust account access (the Tunnel under `tstly.dev` already runs there).
- Coolify dashboard access for the host running the MemPalace fork.
- Working `mempalace` deployment serving `claude-brain.tstly.dev` (last confirmed in deployment session log v1.10–v1.15).
- Editable access to `C:\Users\phatt\Desktop\Claude Workspace\Vikunja Deployment\SECRETS_DO_NOT_COMMIT.md` (the secrets convention's durable-backup file).
- A clean browser (no Cloudflare cookies cached) for testing the OTP flow.

---

## Step-by-step checklist

Each step has a **verification** Matt completes before moving to the next. Drop a screenshot into the placeholder under each step as you go — it's the audit trail for the next deployment-log entry.

### Step 1 · Verify the existing CF Tunnel is healthy

**Action.** From any external network (phone hotspot is fine), run:

```
curl -fsS https://claude-brain.tstly.dev/health
```

**Expected.** HTTP 200, `{"status":"ok"}` or similar.

**Verification.** ✅ Returns 200. ✅ Cloudflare Zero Trust → Networks → Tunnels shows `atlas-dev` (or whichever tunnel routes this hostname) as "Healthy."

**Screenshot placeholder:**
```
[ Screenshot: tunnel health page showing green status ]
[ Screenshot: terminal output showing 200 OK from /health ]
```

---

### Step 2 · Create the CF Access application

**Action.** In Cloudflare Zero Trust dashboard:

1. Access → Applications → **Add an application**.
2. Choose **Self-hosted**.
3. Application name: `MemPalace Atrium`.
4. Session duration: **24 hours** (matches Atlas convention).
5. Application domain: `claude-brain.tstly.dev` (full hostname match, no subpath).
6. Save and continue to policy attachment.

**Verification.** Application appears in Access → Applications list, status "Active."

**Screenshot placeholder:**
```
[ Screenshot: Application configuration page after save ]
```

---

### Step 3 · Attach Policy 1 — Service Auth

**Action.** In the application's Policies tab → **Add a policy**:

1. Policy name: `mempalace-atrium-svc-bypass`.
2. Action: **Service Auth**.
3. Session duration: same as application (24 hours).
4. Configure rule → Selector: **Service Token** → Value: create new token named `mempalace-atrium-svc`.
5. **Capture the Client ID and Client Secret immediately** — Cloudflare shows the secret only once.
6. Save policy.

**Verification.** Policy appears in the application's policy list. **Precedence: Service Auth FIRST** (this matters — Service Auth must be evaluated before the email-OTP policy so that MCP clients with the service-auth headers bypass the OTP challenge).

**Screenshot placeholder:**
```
[ Screenshot: Service Auth policy after save ]
[ Screenshot: Service token list showing mempalace-atrium-svc ]
```

---

### Step 4 · Attach Policy 2 — Allow (email OTP)

**Action.** In the application's Policies tab → **Add a policy**:

1. Policy name: `matt-luke-email-otp`.
2. Action: **Allow**.
3. Session duration: same as application.
4. Configure rule → Include → Selector: **Emails** → Values: `matt@interactep.com`, `luke@interactep.com`.
5. Authentication methods: **One-time PIN** only (uncheck other identity providers — we want OTP, not SSO).
6. Save policy.

**Verification.** Both policies listed in order (Service Auth first, Allow second). Atlas Security Admin Governance v0.1.0 §2 trust-zone rule satisfied: *"Cloudflare edge | Trusted-with-policy | Applies Service Auth + Email OTP policies."*

**Screenshot placeholder:**
```
[ Screenshot: Application policy list showing both policies in correct precedence order ]
```

---

### Step 5 · Store the service-auth token durably

**Action.** Open `C:\Users\phatt\Desktop\Claude Workspace\Vikunja Deployment\SECRETS_DO_NOT_COMMIT.md`. Append a clearly labeled block:

```
## CF Access — claude-brain.tstly.dev (mempalace-atrium-svc)
- Created: 2026-04-2X
- Application: MemPalace Atrium
- Policy: mempalace-atrium-svc-bypass (Service Auth)
- Client ID: <CF_ACCESS_CLIENT_ID>
- Client Secret: <CF_ACCESS_CLIENT_SECRET>
- Rotation due: 2026-10-2X (6 months — adjust per Atlas governance cadence in force)
- Used by: Atrium service-account paths; existing /mcp clients with service-auth headers
```

**Verification.** The file contains the labeled block. The Client Secret is the same string captured in Step 3 (this is the only place it lives once you close the CF dashboard).

**Why this file.** Atlas Security Admin Governance v0.1.0 specifies the durable-backup pattern for secrets used outside of Coolify environment variables — `SECRETS_DO_NOT_COMMIT.md` is the canonical location. The file is in a Workspace-mounted folder that's git-ignored everywhere; the name is the safety rail.

**Screenshot placeholder:** none — don't screenshot the secrets file.

---

### Step 6 · Test the gate — anonymous request returns OTP challenge

**Action.** Open a clean browser (Incognito / Private; or a profile with no Cloudflare cookies). Navigate to:

```
https://claude-brain.tstly.dev/
```

**Expected.** Browser is redirected (HTTP 302) to a Cloudflare Access OTP challenge page asking for an email address.

**Verification.** ✅ Redirect happens (you do not reach the Starlette app). ✅ The challenge page is on a Cloudflare-controlled origin (likely `*.cloudflareaccess.com`). ✅ The form asks for an email.

**Screenshot placeholder:**
```
[ Screenshot: Cloudflare Access OTP challenge page ]
```

---

### Step 7 · Test the gate — email OTP success reaches the Starlette app

**Action.** On the OTP page, enter `matt@interactep.com`. Cloudflare emails an OTP. Enter the OTP.

**Expected.** Browser redirects to `https://claude-brain.tstly.dev/`. The Starlette app responds — currently with **404** on `/` because Atrium isn't built yet. **That 404 is the success signal** — it means CF Access let you through to the app.

**Verification.** ✅ OTP arrives in matt@interactep.com inbox within ~30s. ✅ After entering OTP, browser reaches the Starlette origin. ✅ Response is from the Starlette app (check `Server:` header or the 404 body shape — should be Starlette's default 404, not a Cloudflare error page).

**Screenshot placeholder:**
```
[ Screenshot: OTP email received ]
[ Screenshot: Starlette 404 page after OTP success ]
```

**Repeat for `luke@interactep.com`** to confirm both reviewers can authenticate.

---

### Step 8 · Test the gate — service-auth bypass works for `/mcp`

**Action.** From the laptop (terminal):

```
curl -fsS -X POST https://claude-brain.tstly.dev/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MEMPALACE_BEARER_TOKEN" \
  -H "CF-Access-Client-Id: <CLIENT_ID_FROM_STEP_3>" \
  -H "CF-Access-Client-Secret: <CLIENT_SECRET_FROM_STEP_3>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

**Expected.** HTTP 200, JSON-RPC envelope returned with the 19 `mempalace_*` tools (matching the existing v1.14 smoke test). **No OTP challenge** — the service-auth headers bypass it.

**Verification.** ✅ 200 response. ✅ `tools/list` payload returns 19 tools. ✅ No HTML / Cloudflare login redirect anywhere in the response chain.

**Failure mode to check.** Without the `CF-Access-Client-*` headers, the same curl should now return a Cloudflare HTML page (the OTP challenge served as HTML to non-browser clients) rather than reaching Starlette. If anonymous /mcp still works, **the policies are mis-ordered** — go back to Step 3 and ensure Service Auth precedes Allow.

**Screenshot placeholder:**
```
[ Screenshot: terminal output showing successful tools/list with service-auth headers ]
[ Screenshot: terminal output showing OTP HTML response without service-auth headers ]
```

---

### Step 9 · Document the working state in the deployment log

**Action.** In the Vikunja deployment log (next session entry — v1.16 or whatever's current), add a section:

```
## Phase 11 — CF Access on claude-brain.tstly.dev (Atrium pre-ship gate)
- Date: 2026-04-2X
- Application: MemPalace Atrium (Cloudflare Zero Trust)
- Policies (in precedence order):
  1. mempalace-atrium-svc-bypass (Service Auth — token mempalace-atrium-svc)
  2. matt-luke-email-otp (Allow — emails matt@/luke@interactep.com, OTP only)
- Service-auth token stored: SECRETS_DO_NOT_COMMIT.md
- Verifications passed: Steps 1–8 (see screenshots below)
- Atrium build clearance: GREEN — proceed.
```

Attach the screenshots from Steps 1, 2, 3, 4, 6, 7, 8.

**Verification.** Log entry exists with timestamps, screenshots embedded, and the GREEN clearance line. This is the formal handoff from "operational pre-ship" to "build can begin."

---

## Daily re-test during build

Step 8 is fragile — CF policy edits, token rotation, and dashboard drift can quietly break service-auth bypass. **Re-run Step 8 once a day** during Atrium build. If it ever fails, stop the build, fix the gate, and document.

---

## What this checklist does NOT cover

- **CF Access logout URL** — captured in Atrium PRD §3.3 (Logout row). No setup needed; it's a CF-provided URL.
- **`Cf-Access-Authenticated-User-Email` header forwarding** — Cloudflare adds this header automatically on policy-allow flow. Atrium's middleware reads it (per PRD §3.3 row 3). No setup needed in Cloudflare.
- **Atlas REST API auth** — separate from CF Access. Covered in `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` §5.1 and Atrium PRD §3.3 row 4. The token there is application-layer, not CF-edge.
- **Token rotation** — set a calendar reminder for the rotation date in the SECRETS file. Rotation procedure: re-run Steps 3 and 5, then re-run Step 8 to verify the new token works, then revoke the old token in CF Zero Trust → Service Tokens.

---

End of CF Access Setup v0.1.0.
