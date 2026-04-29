# MemPalace Deployment — Session Log v1.2

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies. build-tester applies. cowork-git-push applies for fork pushes.

> Earlier session-log snapshots: v1.0 (kickoff + Phase 0 audit), v1.1 (architecture pivot + D1 lock).

---

## v1.0 — Session kickoff (2026-04-27)

(See `MemPalace_Deployment_Session_Log_v1.0.md` for the full Phase 0 audit log. Summary: read fork files, audited git/host/corpus, wrote Discovery Report v0.1, hit STOP gate.)

## v1.1 — Architecture pivot + D1 locked (2026-04-27)

(See `MemPalace_Deployment_Session_Log_v1.1.md` for the full pivot rationale and verification findings. Summary: Path A chosen — Coolify is single source of truth, all clients query the hosted instance. D1 locked: palace at `~/.mempalace/palace` *inside the Coolify container*, not on the laptop. Web research confirmed mobile MCP support is real; voice-mode invocation parked for Matt's external test.)

---

## v1.2 — D2 locked (2026-04-27)

### D2 — LOCKED: Bearer-first, OAuth later

**Decision:** The hosted MemPalace MCP server will launch with a **static bearer-token auth** scheme. One secret stored in Coolify env, same secret carried in client configs (Cowork, Claude Code, Claude Desktop). OAuth will be added as a focused workstream once we've (a) proven the architecture end-to-end with bearer auth, and (b) confirmed via Matt's external test thread whether Claude voice-mode tool-invocation is supported.

**Why this and not OAuth-from-day-one:**

- Three of the four near-term clients (Cowork, Claude Code, Claude Desktop) already speak bearer-token MCP today.
- The fourth (Claude.ai web/mobile/voice) is the only one that needs OAuth, AND is the same client where voice-mode is unverified. Engineering OAuth before voice is confirmed risks building auth for a path that doesn't carry the feature Matt actually wants.
- Bearer auth gets MemPalace usable end-to-end in days, not weeks. OAuth becomes a focused, scoped follow-up — not an architecture-blocking dependency.

**Client wire-up order (after Phase 7 deployment):**

1. Cowork — register bearer-MCP entry pointing at the Coolify endpoint.
2. Claude Code — `claude mcp add mempalace --transport http --header "Authorization: Bearer …"` once Code is installed.
3. Claude Desktop — Settings → Connectors with bearer header.
4. *(Pending OAuth, Phase 7.5 or later)* Claude.ai web + mobile + voice.

**Implications:**

- ISSUE-4 narrows: HTTP wrapper still needed; OAuth deferred to Phase 7.5+.
- A single bearer-token secret will be generated (32+ random bytes, base64), stored in Coolify env vars, and copied into each client config. Treat like a password — never committed, never pasted unredacted in chat.
- Anthropic IP allowlisting on the Coolify side is OPTIONAL until OAuth lands and we open up to claude.ai. Until then, the only public-facing risk surface is anyone with the bearer token. Cloudflare Access or a similar IP/geo guard could optionally be layered on `mempalace.tstly.dev` for an extra ring before Phase 7.5.

### Issues carried forward

- ISSUE-1 (open): Pytest 85/85 not re-verified — Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): `python` PATH points at missing UV cpython 3.13.12.
- ISSUE-4 (narrowed): HTTP MCP wrapper needed for Phase 7. OAuth layer deferred.
- ISSUE-5 (parked): Voice-mode tool support — Matt testing externally.

### Versioning policy

Every artifact carries a version stamp in the filename. Decision locks bump the session log minor version. Each previous log version is preserved as a rollback anchor.
