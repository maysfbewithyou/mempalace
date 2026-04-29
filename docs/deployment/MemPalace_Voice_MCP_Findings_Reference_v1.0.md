# MemPalace — Voice / MCP Test Findings Reference (v1.0)

Source: parallel `voice-test-mcp` deployment by Matt, 2026-04-27.
Live test target: `https://voice-mcp.tstly.dev/mcp` (sister project on the same Coolify host).
Repo: https://github.com/maysfbewithyou/voice-test-mcp

This doc preserves the conclusions from a deliberate, magic-token-verified test of whether Claude voice mode can reach custom MCP connectors. The answer was unambiguous; this doc captures it for future-Matt and any future agent picking up the MemPalace deployment.

---

## TL;DR

**Voice mode cannot reach custom MCP connectors today.** Text mode works cleanly across web, Claude Desktop, and mobile. The `/mcp` Streamable HTTP transport pattern (POST + JSON body) is the right protocol. The same Coolify + Cloudflare-tunnel + `localhost:50XX` host-port pattern Matt has proven seven times over for `*.tstly.dev` apps is exactly what hosts MemPalace too.

The architectural call this forces: design MemPalace tools so a single text-mode tool call returns a rich, self-contained chunk of context. Voice mode users will "prep in text, converse in voice" within one chat — no mid-conversation fetches.

---

## Confirmed findings (test-verified, three voice attempts)

| # | Finding | Evidence |
|---|---|---|
| 1 | Voice mode declines custom MCP tools | Three independent voice-only attempts; Claude said its toolset is fixed: web search, get current time, create alarms, create timers. No `tool_search`, no dynamic loading. |
| 2 | Text mode works on web, desktop, **and mobile** | First-ask success in all three. The `/mcp` Streamable HTTP endpoint round-tripped with the magic token + live timestamp on every text-mode test. |
| 3 | Cross-device sync works | Connector added via web shows up on mobile automatically. |
| 4 | Custom connectors require Streamable HTTP, not legacy SSE | Legacy-SSE-only servers return *"Couldn't reach the MCP server."* `/mcp` POST + JSON-RPC body is what Anthropic's connector backend speaks. |
| 5 | Voice declines honestly — no hallucinated tokens | The "do not guess or make up a token" prompt clause was respected every time. Useful UX property. |
| 6 | **Typing during a voice conversation flips that turn to text mode** | Subtle. Cost a misdiagnosis on rev 2 of Matt's test. For voice tests: stay vocal. |
| 7 | Connector setup is web-only; mobile auto-syncs | Settings → Connectors → Add custom connector → URL → name → save. Done. |

---

## Implications for MemPalace's design

### Tool granularity (revise upward)

Prefer **one tool call returning a rich digest** over five small tools returning one item each. Voice-mode users can't iterate via incremental fetches — each fetch needs a text-mode interruption.

For MemPalace this means:

- A `mempalace_brief` (or similar) tool that returns "today's relevant context for X" pre-summarized as a single JSON or markdown chunk. Pull from drawers, halls, knowledge-graph timeline as needed; one call returns the lot.
- The existing `mempalace_search`, `mempalace_status`, etc. stay — but the primary voice-prep workflow uses the brief tool.
- Tools accept rich filters: date range, wing, hall, room, tags. One shot per voice-conversation prep is the budget.

### UX pattern: "prep in text, converse in voice"

1. Open a fresh Claude chat on mobile in **text mode**.
2. Type or paste a prompt that triggers MemPalace queries — e.g., *"Pull from MemPalace: today's vendor decisions, FNB schedule deltas, and any LA Fairgrounds notes."* Tool fires, results land in chat history.
3. Switch to **voice mode** in the same chat. The loaded context is now available as conversation history — voice can answer questions about it without making fresh tool calls.
4. If fresh data is needed mid-conversation: brief switch back to text mode, type the new query, get the result, continue voice.

Designed-around constraint, not a workaround. The pattern is fully reasonable.

---

## What this means for our locked decisions

| Decision | Status after these findings |
|---|---|
| **D2 — bearer-first, OAuth deferred** | UNCHANGED. Cowork/Code/Desktop accept bearer auth. Phase 10 OAuth is for claude.ai web + mobile (text mode) — but voice never reaches custom connectors regardless. |
| **Phase 10 priority** | LOWERED slightly. Phase 10 OAuth enables claude.ai text-mode access. It does NOT unlock voice — that's an Anthropic runtime constraint, not an auth issue. Still worth doing, just not the panacea. |
| **ISSUE-5 (voice mode tool support)** | **RESOLVED with NEGATIVE confirmation.** Voice cannot reach custom connectors today. The `get_voice_test_token` tool that surfaced earlier in the session was Matt's parallel test, not a counter-example. |
| **Existing architecture (A1–A8)** | UNCHANGED. The `/mcp` Streamable HTTP, bearer-token, Coolify, Cloudflare-tunnel, host-port-mapping pattern is exactly what Matt's parallel test confirmed works. Our MemPalace deployment mirrors that pattern. |

---

## Reproducible setup pattern (for MemPalace and any future MCP)

Matt's playbook — proven seven times across `cms-dev`, `events-dev`, `sales-dev`, `voice-mcp`, `claude-brain`, etc. Reproduced here verbatim:

1. New GitHub repo with an MCP server implementing `/mcp` (POST→JSON), `/healthz`, and the tool surface.
2. Coolify → New Project → Public Repository → Dockerfile build pack. Set env vars.
3. Port Mappings: `50XX:<container_port>`. Pick a free `50XX` (taken so far: 5023, 5024, 5035, 5036, 5040, 5042, 5050, 7001).
4. Set FQDN in Coolify General → `https://<name>.tstly.dev`.
5. Deploy. Verify `https://<name>.tstly.dev/healthz` (or `/health`).
6. Cloudflare → Networks → Tunnels → atlas-dev → Routes → Add: subdomain `<name>`, domain `tstly.dev`, type HTTP, URL `localhost:50XX`. Save (DNS auto-creates).
7. `curl https://<name>.tstly.dev/healthz` returns 200.
8. Claude → Settings → Connectors → Add custom connector → URL `https://<name>.tstly.dev/mcp` → name → save.
9. Test in text chat first. Voice second (and accept that custom-connector tools won't be reachable).

Total time per new integration: ~15–30 min once the server code is written.

---

## When voice mode DOES gain custom-connector access

Anthropic has been given feedback. When the runtime adds support, the prep-then-voice pattern becomes optional, not required. MemPalace tools designed under the "rich one-shot" principle still work fine — they just become callable mid-voice-conversation.

The simplest day-zero retest: ask Claude voice mode to call `mempalace_status`. If it returns the live wing/hall/drawer counts without a typed prompt, the constraint has lifted.

---

## Filed for the deployment record

This doc joins `MemPalace_Cowork_Kickoff_v1.0.md`, `HARDENING_CHANGELOG.md`, the `MemPalace_Phase_*` docs, and the session-log series in the fork. Phase 9 closeout will move them all to `docs/deployment/` and commit them to git history.
