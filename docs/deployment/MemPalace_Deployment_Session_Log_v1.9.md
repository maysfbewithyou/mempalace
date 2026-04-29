# MemPalace Deployment — Session Log v1.9

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Upstream: https://github.com/MemPalace/mempalace.git
Governance: NOT Atlas. Versioning protocol applies.

> Earlier session-log snapshots: v1.0–v1.8.

---

## v1.0–v1.8 — Summary (all 9 decisions complete with v1.9)

- v1.0: Phase 0 audit, Discovery Report v0.1, STOP gate.
- v1.1: D1 — Path A, Coolify single source of truth.
- v1.2: D2 — bearer-token auth first; OAuth deferred.
- v1.3: D3 — four wings: `wing_mega`, `wing_iep`, `wing_atlas`, `wing_personal`.
- v1.4: D4 — Claude.ai export requested; mine when it arrives.
- v1.5: D5 — Slack deferred to Phase 9.
- v1.6: D6 — Phase 8 closeout: tag + commit docs + delete stale branch.
- v1.7: D7 — Hybrid hooks + scheduled weekly agentic review.
- v1.8: D8 — Monthly upstream sync + manual merges + scheduled monthly diff report.

---

## v1.9 — D9 locked + all decisions complete (2026-04-27)

### D9 — LOCKED: Draft C (rich identity, ~95 tokens)

**`~\.mempalace\identity.txt`:**

```
I am Matt Mays' memory palace. Matt operates MEGA Entertainment (parent
corp), runs IEP — Interactive Event Productions — for event production
ops, and is building Atlas, the internal software system across the
businesses. Four wings: wing_mega (corporate), wing_iep (events ops),
wing_atlas (software / dev), wing_personal. Twelve halls common to every
wing: events, venues, vendors, timelines, budgets, team, clients,
productions, equipment, creative, technical, and the always-present diary.
Save verbatim — never summarize, never paraphrase. Always search the palace
before answering questions about Matt's work.
```

**Filed to:** `~\.mempalace\identity.txt` during Phase 3 (`mempalace init` + identity wiring), with permissions `0o600` per Hardening Fix #7. Also referenced in the L0 layer of the wake-up sequence per `mempalace.layers.MemoryStack.wake_up()`.

### Decision lock summary (D1–D9, all locked)

| # | Decision | Locked value |
|---|---|---|
| D1 | Palace location | Coolify host, Docker volume `/data/.mempalace/palace` (in-container `~/.mempalace/palace`) — Path A single source of truth |
| D2 | Consumption / auth | Bearer-token first (Cowork, Code, Desktop); OAuth wrapper deferred to Phase 10 (claude.ai web/mobile/voice) |
| D3 | Wings | `wing_mega`, `wing_iep`, `wing_atlas`, `wing_personal` |
| D4 | Claude.ai exports | Request fresh export now via Settings → Privacy → Export data; mine on arrival |
| D5 | Slack exports | Deferred to Phase 9 |
| D6 | GitHub fork posture | Phase 8 closeout: commit docs to `docs/deployment/`, tag `v3.0.14-iep-hardened`, delete `security/hardening-v3` branch |
| D7 | Hooks scope | Hybrid: user-global PreCompact + project-level Stop on three high-value repos; weekly scheduled agentic review |
| D8 | Upstream sync | Monthly cadence + on major-version bumps; all merges manual; monthly scheduled diff report |
| D9 | Identity layer | Draft C — rich (~95 tokens) — content above |

### Updated Phase Plan (v1.0 deployment + post-v1.0 follow-ups)

Reordered from the kickoff to reflect Path A (Coolify must come before mining):

| Phase | Goal | Gate |
|---|---|---|
| 1 | Local install + pytest verify (laptop only — no palace yet) | **85/85 pytest pass** |
| 2 | Coolify deployment: build HTTP wrapper around `mempalace.mcp_server`, bearer-auth, Cloudflare tunnel at `mempalace.tstly.dev`, Docker container with palace volume | Tunnel returns 200 on health check; bearer auth rejects unauth'd; one MCP tool round-trips end-to-end |
| 3 | `mempalace init` against hosted palace via remote-aware client; write `identity.txt`; create four wings; verify wing structure | `mempalace status` (over MCP) shows four wings, default halls populated |
| 4 | Mine selected `Claude Projects/` subdirs into hosted palace (skip Event Guy University); explicit `--wing` per subdir per D3 routing | Sample search returns relevant verbatim drawers from each wing |
| 5 | Mine `atlas/` codebase to `wing_atlas`; verify cross-wing tunnel between `wing_iep` and `wing_atlas` lights up | Cross-wing tunnel test passes |
| 6 | When Claude.ai export ZIP arrives: split mega-files, mine `--mode convos --extract general` into appropriate wings | Search recovers known past conversation |
| 7 | Install Claude Code (`npm install -g @anthropic-ai/claude-code`); register bearer-MCP for hosted MemPalace; verify end-to-end query through Code | Code session asks a memory question; gets verbatim drawer back |
| 8 | Wire hooks (D7 hybrid scope) + create scheduled review tasks (D7 weekly hook review + D8 monthly upstream diff) | Hooks fire on a test session; scheduled tasks list shows both entries |
| 9 | Closeout: move docs to `docs/deployment/`; tag `v3.0.14-iep-hardened`; delete stale branch | Tag visible on github.com; clean `git status`; `docs/deployment/` populated |
| **Post-v1.0** | | |
| 10 | OAuth wrapper for claude.ai web/mobile/voice clients (D2 follow-up) | Custom connector adds successfully on claude.ai; voice-mode test (per Matt's other thread) confirmed |
| 11 | Slack mining (D5 follow-up) | Workspace export landed and mined into `wing_iep` |

### Known issues going into Phase 1

- ISSUE-1 (BLOCKER): Pytest 85/85 not re-verified. Matt to run `pytest tests/ -v` in his own terminal before Phase 1 begins. Cowork's Python invocation is hung by a broken Windows-MCP venv pointer.
- ISSUE-2 (Phase 7 dep): `claude` CLI not installed. Will install via npm in Phase 7.
- ISSUE-3 (cosmetic): stale `python` PATH entry pointing at missing UV cpython 3.13.12.
- ISSUE-4 (Phase 2 work): HTTP MCP wrapper needs to be designed and built. New code, not in upstream.
- ISSUE-5 (parked, Phase 10): voice-mode tool support — Matt testing externally.
- ISSUE-6 (parked, Phase 6): Claude.ai export ZIP awaited.
- ISSUE-7 (parked, Phase 11): Slack mining design.
- ISSUE-8 (Phase 8): Verify Stop hook merge behavior before installing hybrid scope.

### Versioning policy

Every artifact carries a version stamp. Decision locks bump session-log minor version. Each prior log version preserved as a rollback anchor. With v1.9, D1–D9 are all locked; subsequent log versions track Phase execution rather than decision discovery.
