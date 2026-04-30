# MemPalace Deployment - Session Log v1.16

Project: MemPalace fork (IEP-personalized AI memory system)
Working tree: `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`
Origin: https://github.com/maysfbewithyou/mempalace.git (branch `main`)
Status: **Phases 4-9 + 4a-recovery closed; v3.0.14-iep-hardened and v3.0.14-iep-hardened.2 tagged and pushed**

> Earlier session-log snapshots: v1.0-v1.15.

---

## v1.16 - Phases 4-9 + 4a-recovery closeout (2026-04-28 to 2026-04-29)

### Scope

The successor to v1.15. v1.15 left things at "staging complete; hosted ingest deferred" - Cowork couldn't reach `claude-brain.tstly.dev`, the MemPalace connector wasn't bound, and a static bearer wasn't in scope. v1.16 covers everything between then and the production milestone tag: actually mining the staged corpus into the hosted palace, mining the rest of Matt's Atlas working sets, wiring up Claude Code, registering the monthly upstream sync review, committing the deployment-arc docs, tagging `v3.0.14-iep-hardened`, and closing the rate-limit gap with a follow-up tag `v3.0.14-iep-hardened.2`.

### What was done in this session

**Phase 4a - Mine the fork tree itself (wing_atlas)**

The first real exercise of the hosted palace. Used `tools/remote_mine.py` v0.1 (newly written) against `C:\Users\phatt\Desktop\Claude Workspace\mempalace-fork\`. Started at 6 drawers (1 ChromaDB warmup + 5 from a hand-test) and walked the fork's visible files. Filed **209 of 242** dry-run candidates before the launching shell exited silently - `Start-Process -RedirectStandardOutput` was buffering stdout and never flushed, so when the process terminated we had a 0-byte log and no diagnostic trail. Lesson recorded; closed by 4a-recovery later in this same log.

**Phase 4b - Mine Claude Projects subdirectories (wing_atlas)**

Walked `C:\Users\phatt\Desktop\Claude Workspace\Claude Projects\` (32 Atlas-side project subdirs). Dry-run found 779 candidates after default skips (`.git`, `node_modules`, binaries, Office formats). Real mine ran for **15 minutes at ~0.9 rps**, filed all **779 with 0 errors**, 25 binaries skipped, 151 truncated at 100KB cap. Palace went **6 -> 770 drawers** (218 dedup'd by upstream `add_drawer`'s internal similarity check - same content reused across project directories, e.g. README templates).

**Phase 5 - Mine the atlas codebase (wing_atlas)**

Walked `C:\Users\phatt\Documents\GitHub\atlas\`. Pre-mine sweep confirmed only one risky file (`instance/inventory.db` - a 20KB SQLite blob caught by binary detection). 18 minutes at ~0.9 rps. Filed **888 of 888 attempted, 7 errors** (rate-limit bursts in `templates/erp/dfg/` and `templates/erp/invoices/` - the upstream `RateLimiter` is hardcoded at 60 req/min and 0.9 rps with the embedding pipeline being warm equals occasional 60s windows that exceed the cap). 1 binary skipped (the SQLite). 43 truncated. Palace went **770 -> 1535 drawers** (net +765 after dedup).

**Phase 6 - Mine Claude.ai export (wing_atlas, wing_iep, wing_personal, wing_mega)**

The export ZIP from v1.15 was extracted, then `split_export.py` (new helper) wrote the 69 conversations as 69 standalone `.md` files sorted chronologically. Triaged into three buckets by title regex:

| Bucket | Count | Wing |
|---|---|---|
| IEP-specific (`IEP_subcontractor_agreement_for_LA_Fairgrounds`) | 1 | wing_iep |
| Atlas-related (Sales App, Production Schedule, Site Plan, Catering, Waiver, TECH-04..07, CMS, Executive App, MemPalace integration, etc.) | 50 | wing_atlas |
| Personal (AI Teach, Yu-Gi-Oh, Pythagoras viz, Cowork bug threads, untitled fragments) | 18 | wing_personal |

All three buckets mined cleanly, **0 errors**. Palace went **1535 -> 1604 drawers**.

The export's two non-conversation files were filed directly via `mempalace_add_drawer` (no walk needed):

- `memories.json` -> `wing_mega/claude-ai-memories` (the persistent "what does Claude remember about me" summary - Matt's role, IEP team, Atlas tech-stack correction, governance rules, top-of-mind work items).
- `projects.json` -> `wing_mega/claude-ai-projects` (a formatted index of Matt's 7 Claude.ai projects).

Final after the wing_mega adds: **1606 drawers across all 4 locked wings**.

**Phase 7 - Install Claude Code + connect bearer-MCP**

Discovery: `claude.exe` 2.1.119 was already at `%APPDATA%\Claude\claude-code\2.1.119\claude.exe` (254 MB, not in PATH). Verified `--version` and that `mcp list` returned no servers. Registered MemPalace at user scope:

```
claude mcp add --transport http --scope user mempalace https://claude-brain.tstly.dev/mcp \
  --header "Authorization: Bearer <token-from-~/.mempalace_client/token>"
```

Health check: **Connected**. The connector is now available across every project Matt opens with Claude Code.

**Phase 8 - Hooks (D7) + scheduled agentic review (D8)**

Built `tools/claude-mempalace-hook.ps1` - a small PowerShell hook that reads the Claude Code event JSON from stdin, encodes wing/cwd/event/session-id as an AAAK-flavored pipe-separated entry, and POSTs to `mempalace_diary_write` with `agent_name="claude-code"`. Iterations:

- v1.0 used `wing` + `agent` arg names (rejected by upstream's schema, which requires `agent_name`).
- v1.1 added BOM/whitespace stripping after JSON-parse failures on real stdin.
- v1.2 fixed stdin reading (try `[Console]::In.ReadToEnd()` first, fall back to `$input | Out-String`).
- v1.3 corrected schema (`agent_name`, `entry`, optional `topic`).

End-to-end smoke test (`cmd /c type | powershell -File hook.ps1`) returned `http=200` and the entry was readable back via `mempalace_diary_read agent_name=claude-code`. Wired into `.claude/settings.local.json` for both the fork and `C:\Users\phatt\Documents\GitHub\atlas\` (Stop + PreCompact matchers, both gitignored as user-local).

For D8 (monthly upstream sync cadence), created scheduled task `mempalace-upstream-sync-review` via the Cowork scheduled-tasks MCP. Cron `0 9 1 * *` (1st of month, 9am local). Read-only review: fetch upstream/main, diff against fork's last sync, categorize unmerged commits (critical / recommended / nice-to-have / skip), file the summary as a `claude-code` diary entry under topic `upstream-sync-review`, and only DM Slack on critical findings. Does **not** run merges - Matt drives those manually.

**Phase 9 - Closeout commit + tag + branch cleanup**

Untracked-cleanup pass:

- 24 `MemPalace_*.md` documents at the fork root -> moved to `docs/deployment/`.
- New `.claude/` (project-scoped settings.local.json) -> added to `.gitignore` (user-local, not committed).
- `tools/claude-mempalace-hook.ps1` and `tools/remote_mine.py` (both untracked from this session) -> committed.
- `docs/architecture/` (storage audit + CF Access setup) and `docs/ui/` (discovery + PRD + mockups + atrium handoff) - both already existed but had never been committed; added now.
- `_phase4_*` staging artifacts, `pytest-cache-files-*`, hook log -> all added to `.gitignore`.

**Commit `229a93e`** - 33 files, +5,156 lines.

**Annotated tag `v3.0.14-iep-hardened`** (production milestone). Stack summary, locked decisions D1-D9 reference, palace-state snapshot (1606 drawers across 4 wings).

**Pushed:** main, tag, and a delete of the stale `origin/security/hardening-v3` branch.

**Phase 4a-recovery - Patch + close the rate-limit gap**

The Phase 4a/5 mines together dropped 40 drawers (33 from the fork mine when `Start-Process` swallowed the diagnostic trail, 7 from the atlas mine in a tight `templates/erp/dfg/` + `invoices/` rate-limit cluster). Patched `tools/remote_mine.py` to v0.2:

| Change | Old | New |
|---|---|---|
| Default `--rps` | 0.9 (= 54/min) | 0.7 (= 42/min) |
| Throttle key | `n_filed` | `n_calls` (so `--check-duplicate`'s extra calls pace correctly) |
| New flag | - | `--check-duplicate` (off by default; on, calls `mempalace_check_duplicate` first and skips matches at `--dupe-threshold`) |
| New flag | - | `--dupe-threshold` (default 0.9) |
| New stat line | - | `skipped (dupe): N` |
| User-Agent | `mempalace-remote-miner/0.1` | `mempalace-remote-miner/0.2` |

Bumped pyproject local version `3.0.14+iep.1` -> `3.0.14+iep.2`.

Re-ran the four affected directories with `--check-duplicate --rps 0.4` (halved to absorb the 2x call count):

| Dir | Wing | Filed | Dupe-skipped | Errors |
|---|---|---|---|---|
| `_phase4_v010_full` | wing_atlas | 33 | 28 | 0 |
| `_phase4_v010_slice` | wing_atlas | 5 | 0 | 0 |
| `atlas/templates/erp/dfg` | wing_atlas | 28 | 1 | 0 |
| `atlas/templates/erp/invoices` | wing_atlas | 1 | 1 | 0 |
| **Totals** | | **67** | **30** | **0** |

Total runtime: 7m 30s. Notable: of the **67 client-filed**, only **29 stuck** in the palace (1606 -> 1635). The other **38 were dedup'd by upstream `add_drawer`'s internal similarity check** - meaning the upstream dedup is stricter than the 0.9 threshold the client uses. This is fine; it confirms `--check-duplicate` is for *audit visibility*, not for correctness. Going forward, default usage stays `--rps 0.7` without `--check-duplicate`.

**Commit `8b7e2eb`** - 2 files, +103/-23.
**Annotated tag `v3.0.14-iep-hardened.2`** (recovery follow-up).
**Slack notify** to `#atlas-updates` (private channel, no Luke ping per Matt's instruction for tooling-only changes).

### Final palace state (post-recovery)

| Wing | Drawers |
|---|---|
| wing_atlas | 1613 |
| wing_iep | 1 |
| wing_personal | 18 |
| wing_mega | 2 |
| wing_claude-code | 1 (hook smoke test - see "Open items") |
| **Total** | **1635** |

171 rooms. Top rooms by drawer count: `js` (109), `atlas` (95), `models` (79), `versions` (72), `events-app` (60), `css` (59), `routes` (52), `mempalace-fork` (44), `services` (42), `phase4-v010-full` (41).

### Hook diary state

`mempalace_diary_read agent_name=claude-code` returns the smoke-test entry from 2026-04-28: `EVT:Stop | WING:wing_atlas | CWD:mempalace-fork | SID:deadbeef | TS:...`. This is the first real entry. Real Claude Code Stop/PreCompact events will append to this same agent diary going forward.

### Scheduled task state

`mempalace-upstream-sync-review` is registered, enabled, next run **2026-05-01 09:00** (local). Skill file at `C:\Users\phatt\Documents\Claude\Scheduled\mempalace-upstream-sync-review\SKILL.md`. The task has not been pre-run via "Run now" - recommend doing so once before its first scheduled fire so any tool permissions get pre-approved.

### Cleanup pass (Cowork session 2026-04-29)

1. Considered deleting the `wing_claude-code/warmup` smoke-test drawer; **kept**. The `mempalace_search` tool's response shape doesn't include `drawer_id`, only wing/room/source_file/similarity, so direct deletion via `mempalace_delete_drawer` isn't reachable from search. More importantly, on reflection it's a legitimate first datapoint in the wing - every future Claude Code Stop/PreCompact event appends here. Removing it would just clear evidence that the wiring works.
2. Swept all `_phase4_*` staging artifacts and `pytest-cache-files-*` from the fork (~3.4 MB total: `_phase4_v010_full/` 3.25 MB, `_phase4_v010_slice/` 116 KB, the manifest, the run log, the readme, the inspect/stage scripts, the zip report, the pytest cache). All gitignored, so working tree stayed clean. Disk-only cleanup; nothing in git changed.
3. **This file.**

### Decisions during this arc that didn't make it into D1-D9

These came up after Phase 0 lock-in and were resolved by the obvious cheap default. Recording for the audit trail:

| Topic | Resolution |
|---|---|
| Wing for Claude.ai `memories.json` | wing_mega/claude-ai-memories (cross-cutting identity context, not project-specific) |
| Wing for Claude.ai `projects.json` | wing_mega/claude-ai-projects (formatted index of Matt's 7 Claude.ai projects) |
| Wing for personal Claude.ai conversations | wing_personal (Yu-Gi-Oh, AI Teach, untitled fragments) |
| Hook agent_name | `claude-code` (separate from claude.ai's `claude-web` diaries) |
| Project-scoped hooks committed or local? | `.claude/settings.local.json` - gitignored, user-local. The hook script itself is committed at `tools/claude-mempalace-hook.ps1`. |
| Slack ping policy | DM Luke only on operational/critical changes. Tooling and version bumps post to `#atlas-updates` without a ping. |
| Tag for the recovery follow-up | Yes - `v3.0.14-iep-hardened.2`. Track every change. |

### Known nits (low-priority, carried forward)

- **`<NUL` artifact in commit messages** from the GitMcpFix shim - visible in `git log --oneline` for some Phase 10 commits. Cosmetic; commits work fine. One-line shim patch.
- **WWW-Authenticate header scheme** - OAuth metadata response sometimes returns `http://` in the realm URL where it should be `https://`. Doesn't break Anthropic Connectors (they're tolerant). Cosmetic.
- **`mempalace_search` returns no `drawer_id`** in the result rows - only wing/room/source_file/similarity/text. Means deletion-by-search isn't possible from the MCP surface. Either upstream issue or schema gap. Workaround: use the CLI directly on the Coolify host if surgical drawer deletion is ever needed.
- **`mempalace_check_duplicate` at 0.9 threshold misses near-duplicates** that upstream `add_drawer`'s internal dedup catches at a stricter threshold. Confirmed during recovery (67 client-filed -> 29 stuck -> 38 caught). Not actionable - upstream's behavior is the right one for storage; the client-side flag is for audit visibility only.
- **Phase 11 - Slack mining (deferred from D5).** Carried forward.

### Versioning policy (carries over from v1.15)

Phase sub-versions track ingest milestones, not infrastructure. Production tags follow git semver with the IEP local-version suffix (`v3.0.14-iep-hardened` for the deployment milestone, `.2` suffix for the recovery follow-up). Matt's "track every change" preference: every code-touching commit gets a tag, even if it's a small follow-up - same milestone family with `.N` suffix is preferred over a brand-new tag family.
