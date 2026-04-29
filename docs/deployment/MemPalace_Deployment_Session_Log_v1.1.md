# MemPalace Deployment — Session Log v1.1

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies. build-tester applies. cowork-git-push applies for fork pushes.

---

## v1.0 — Session kickoff (2026-04-27)

### Phase 0 — Discovery audit (no installs)

- v0.1 — Read priority fork files: README.md (head), HARDENING_CHANGELOG.md (full), pyproject.toml, CONTRIBUTING.md, mempalace/cli.py, mempalace/config.py, hooks/mempal_save_hook.sh, hooks/mempal_precompact_hook.sh. Confirmed: 16 hardening fixes + 5 IEP personalizations are present in the working tree (config.py shows event-production wings, hooks have LF endings, pyproject pinned chromadb 0.5.23-0.6).
- v0.2 — Audited fork git state via .git plumbing files (git CLI hung under Windows-MCP — see Issues). Confirmed: HEAD on `main` at 252e440df5f8c13a7600d853fd54adbef6e59dbe; origin/main matches → hardening commits already pushed. Separate `security/hardening-v3` branch exists on origin (1f06c12...). upstream/main at 298143... Tags v3.0.0 and v3.1.0 present (from upstream lineage). Working tree was a fresh clone — no local commits ahead of origin/main. Untracked items: MemPalace_Cowork_Kickoff_v1.0.md, .pytest_cache/ (gitignored), pytest-cache-files-hzcavgs3/ (not gitignored).
- v0.3 — Audited host environment. Findings: Python 3.14.3 installed at `C:\Users\phatt\AppData\Local\Programs\Python\Python314\python.exe`; uv 0.11.3; node v24.14.0; coolify.interactep.app reachable (HTTP 200); github.com reachable. Disk free 83.9 GB. Issues found: (a) `python` on PATH resolves to a non-existent UV-managed cpython 3.13.12 — broken pointer; (b) `VIRTUAL_ENV` env var inherited from Windows-MCP points at a broken venv trampoline, which makes Python hang when invoked via `-c` or `-m` from this session; (c) `claude` CLI is NOT installed (no PATH match, no npm dir under AppData\Roaming\npm).
- v0.4 — Audited corpus to mine. Claude Projects: 12,361 MB across 1,542 files (Event Guy University alone is 11.5 GB — likely media, recommend skip). Atlas: 49.2 MB / 928 files (small, code-rich, prime mining target). mempalace-fork itself: 2.3 MB / 128 files. No Claude.ai chat exports or Slack exports found in standard locations.
- v0.5 — Wrote Discovery Report at `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\MemPalace_Phase_0_Discovery_v0.1.md`. STOP gate engaged — awaiting Matt's approval and D1–D9 decisions before Phase 1.

---

## v1.1 — Architecture pivot + D1 locked (2026-04-27)

### Architectural pivot — Path A (Coolify single source of truth)

Matt expanded the deployment goal mid-walkthrough: the palace must be reachable from his **phone (Claude Chat mobile app)**, including ideally during voice chats, so MemPalace can be queried in voice conversations. This changes the architecture from "local CLI tool" to "hosted service that all clients query," and promotes the formerly-deferred Coolify deployment from Phase 7-optional to Phase 0-mandatory.

The three architectural choices on the table:
- **Path A** — Coolify is the single source of truth; all clients (laptop CLI, Cowork, Claude Code, Claude.ai web/desktop, Claude mobile) talk to one hosted instance. No sync logic. Loss: laptop offline = no memory.
- **Path B** — Local is master; Coolify is a periodic read-only mirror. ChromaDB doesn't multi-master, so writes can only happen locally.
- **Path C** — Both write, periodic merge. Real engineering, ruled out for v1.

**Matt's decision: Path A.** Single palace, single truth, every client connects over the public Coolify endpoint.

### Verification of Path A feasibility (web research, 2026-04-27)

Read both Anthropic support articles on custom remote MCP connectors. Findings:

- ✅ Custom remote MCP connectors are supported on Claude.ai web, Cowork, Claude Desktop, **and Claude mobile (iOS + Android)**, on Free/Pro/Max/Team/Enterprise plans (Free capped at 1 connector). Feature is currently flagged "beta."
- ✅ Mobile gets MCPs via web-side configuration that auto-syncs to mobile (you cannot add an MCP from the phone itself).
- ✅ The connection is initiated **from Anthropic's cloud infrastructure** — not from the user's device — meaning the MCP server must be reachable over the public internet from Anthropic's published IP ranges (and can be firewalled to those ranges).
- ⚠️ **OAuth is the only auth mechanism documented.** No static-bearer / API-key shortcut is mentioned in the support articles. We need to either implement OAuth in the wrapper or find a personal-use shortcut.
- ⚠️ **Voice-mode tool invocation is NOT addressed in the two support articles I read.** Matt is testing this in a parallel thread; if voice doesn't carry through, text chat on mobile still does — Path A still wins.
- Setup is web-only: Customize → Connectors → "+" → Add custom connector → enter remote MCP URL → optional OAuth Client ID/Secret → Add.

### D1 — LOCKED

**Decision:** Authoritative palace lives on the **Coolify host** (`coolify.interactep.app`) inside a Docker volume mounted at `/data/.mempalace/palace` (in-container path resolves to `~/.mempalace/palace` for the in-container user, satisfying Hardening Fix #14's "MEMPAL_DIR must be under $HOME" check). Local laptop CLI does NOT host its own palace; it talks to the hosted instance.

**Implications cascading from D1:**
- Phase 7 (Coolify deployment) is no longer optional and no longer last; it must happen before mining (Phases 3 and 4) so we can mine *into* the hosted palace.
- We need an HTTP transport wrapper around `mempalace.mcp_server` (which is stdio-only upstream).
- We need an OAuth provider in front of the wrapper (or a documented personal-use bypass — to be researched).
- Mining commands (`mempalace mine ...`) need to point at the hosted palace, not a local one. Either via a remote-aware CLI flag or via running mining inside the container.
- D2 (consumption pattern) is now narrowed: Cowork, Claude Code, Claude.ai web, and Claude mobile all connect via the public Coolify endpoint. The only question for D2 is auth + transport details, not which clients.

### Issues carried forward from v1.0

- ISSUE-1 (open): Pytest 85/85 not re-verified — still a Phase 1 gate.
- ISSUE-2 (open): `claude` CLI not installed.
- ISSUE-3 (cosmetic): `python` on PATH points at missing UV cpython 3.13.12.
- ISSUE-4 (NEW): No HTTP/OAuth wrapper exists in the upstream fork. Net-new code we'll have to add (or pull from a framework like FastMCP / mcp-server-starlette / similar).
- ISSUE-5 (NEW, parked): Voice-mode tool support unverified. Matt testing externally. Does NOT block deployment.

### Versioning policy

Every artifact carries a version stamp in the filename. Decision locks bump the session log minor version (v1.0 → v1.1 for D1 lock). Major version bumps reserved for phase transitions or destructive changes. Discovery Report is at v0.1; will reissue as v0.2 if architecture changes invalidate it materially.
