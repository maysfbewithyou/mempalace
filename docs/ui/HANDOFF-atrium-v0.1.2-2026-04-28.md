# Atrium v0.1.2 — Session Handoff for the MemPalace Task Thread

| Field | Value |
|---|---|
| Date | 2026-04-28 |
| Session | Cowork — Atrium UI design v0.1.0 → v0.1.1 → v0.1.2 |
| Operator | Matt |
| Surface | MemPalace UI (Atrium) + shared agent activity ledger (used by Atrium AND the upcoming Atlas project-track tool) |
| Status | Design phase complete. Ready to hand to build. |

---

## What changed in this session

### Round 1 — v0.1.0 design

Three foundational docs landed at `Claude Workspace\mempalace-fork\docs\ui\`:

- `01-mempalace-ui-discovery-v0.1.0.md` — Phase 0 inventory of what already exists in the MemPalace fork.
- `02-mempalace-ui-prd-v0.1.0.md` — Phase 1 PRD: 8 screens, architecture recommendation, tech stack, governance citations, open questions.
- `03-mempalace-ui-mockups-v0.1.0.md` — Phase 2 ASCII wireframes + Mermaid flows for all 8 screens.

### Round 2 — Matt's three v0.1.1 directives

1. **Tool name locked: Atrium.** No further discussion in v1.
2. **CF Access on `claude-brain.tstly.dev` is a hard pre-ship gate.** Service-auth + email-OTP for matt@/luke@. Operational checklist authored for Matt to run at his laptop.
3. **Pull the formal agent activity ledger schema forward into v0.1.0.** No more deferring `agent_runs` / `agent_suggestions` / `agent_reviews` / `agent_persona_registry` to v0.2.0 — designed once and shared with the upcoming Atlas project-track tool.

These three folded into v0.1.1 of all three UI docs (in-file stamp; filenames retained), produced a **new shared schema doc**, and produced a **standalone CF Access setup operational note**.

### Round 3 — Matt's three Q&A on the v0.1.1 open questions

1. **Persona registration ceremony** (Q10) → Hybrid model: YAML in Atlas repo + bootstrap script + live editor in Atrium/project-track Settings + **block-by-default** for unregistered agents. Specified in PRD §13.
2. **Atlas API build order** (Q9) → Critical-path-serial with parallel tracks. Atlas endpoints are the gating critical path; Atrium UI shell + CF Access setup + static read screens run in parallel; integration step waits on the merge. Specified in PRD §12.
3. **Service-token sharing model** (Schema Q3) → **More secure option picked.** Per-session per-operator Atlas tokens minted via `POST /api/auth/exchange` when the operator authenticates through CF Access. Atrium's only long-lived secret is the bootstrap exchange token. Specified in PRD §3.3 row 4 + Schema §5.1.

These three folded into v0.1.2 of the PRD + Mockups, and v0.1.1 of the Schema doc.

---

## Final document set (canonical, to archive)

| File | Path | In-file version |
|---|---|---|
| Discovery | `Claude Workspace\mempalace-fork\docs\ui\01-mempalace-ui-discovery-v0.1.0.md` | **v0.1.1** |
| PRD | `Claude Workspace\mempalace-fork\docs\ui\02-mempalace-ui-prd-v0.1.0.md` | **v0.1.2** |
| Mockups | `Claude Workspace\mempalace-fork\docs\ui\03-mempalace-ui-mockups-v0.1.0.md` | **v0.1.2** |
| Shared ledger schema | `Claude Workspace\Claude Projects\Governance Documents\Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` | **v0.1.1** |
| CF Access setup | `Claude Workspace\mempalace-fork\docs\architecture\03-cf-access-setup-v0.1.0.md` | **v0.1.0** (no change since first authoring) |
| This handoff | `Claude Workspace\mempalace-fork\docs\ui\HANDOFF-atrium-v0.1.2-2026-04-28.md` | new |

(Filenames retained per convention. Canonical version stamp lives in the file header.)

---

## Resolved decisions (locked in v0.1.2)

| # | Decision | Where it's specified |
|---|---|---|
| 1 | Tool name: **Atrium** | All three UI docs, header + body |
| 2 | CF Access service-auth + email-OTP on `claude-brain.tstly.dev` is a HARD pre-ship gate | PRD §3.3 + §3.3.1 + standalone CF Access setup doc |
| 3 | Formal ledger schema (`agent_runs` / `agent_suggestions` / `agent_reviews` / `agent_persona_registry`) in v0.1.0 of Atrium | PRD §6.6 + §6.7 + Schema doc (entire) |
| 4 | Ledger lives in **Atlas Postgres** | Schema §2 |
| 5 | Schema is **shared with the upcoming Atlas project-track tool** | Schema §1, §4; PRD §10 |
| 6 | Build order: Atlas endpoints critical path; Atrium shell + CF Access + static reads in parallel | PRD §12 |
| 7 | Persona registration: YAML + bootstrap script + Settings editor + block-by-default | PRD §13; Schema §3.4 + §7 step 2 |
| 8 | Service-token model: per-session per-operator tokens via `/api/auth/exchange` | PRD §3.3 row 4; Schema §5.1 + §5.2 |

---

## Still open (carried into next round)

| # | Question | Where flagged |
|---|---|---|
| PRD-4 | Knowledge-graph viz priority — confirm Cytoscape deferred to v0.2.0+? | PRD §11 Q4 |
| PRD-5 | Delete/edit-from-Library — keep all mutations through Suggestions, or expose direct delete for Matt-himself? | PRD §11 Q5 |
| PRD-6 | Governance citations — ship build before backfill, or wait for UI/UX v1.5 + AI Agentic v2.2 + API Doc v0.1.0? | PRD §11 Q6 |
| PRD-7 | Voice mode hand-off — out of scope for v0.1.0 Atrium, just flagged | PRD §11 Q7 |
| PRD-8 | Live update cadence — 1s / 5s / 15s HTMX refresh? | PRD §11 Q8 |
| Schema-2 | Direct DB read from project-track vs API-only — keep asymmetry, or uniformly API-mediated? | Schema §8 Q2 |
| Schema-4 | `auto` governance tier — hard cap (Matt-only promotion) or score-driven? | Schema §8 Q4 |
| Schema-6 | Table naming — `agent_runs` etc. (current) or `agent_ledger.runs` (schema-namespaced)? | Schema §8 Q6 |

---

## Pre-build checklist (the things that gate the build)

Before any code is written for Atrium:

1. **Matt runs the CF Access setup operational note** at his laptop — all 9 steps green, screenshots captured, deployment-log entry written. Reference: `Claude Workspace\mempalace-fork\docs\architecture\03-cf-access-setup-v0.1.0.md`.
2. **Atlas Postgres ledger schema migration** lands per Atlas's alembic chain. Tables: `agent_runs`, `agent_suggestions`, `agent_reviews`, `agent_persona_registry`. Reference: `Atlas_Agent_Activity_Ledger_Schema_v0.1.0.md` §3.
3. **`agent_personas.yaml` + `bootstrap_personas.py`** committed to the Atlas repo. Initial seed roster confirmed by Matt. Reference: PRD §13.2.
4. **Atlas REST endpoints** (`/api/auth/exchange`, `/api/agent-ledger/*`) implemented and smoke-tested with curl from `claude-brain.tstly.dev`. Reference: Schema §5.

Once 1–4 are green, Atrium build can begin. PRD §12 specifies which Atrium tracks can run in parallel with each Atlas track.

---

## Skill chain notes

This session did design work only — no code, no migrations, no SQL. So the canonical Atlas skill chain (atlas-delivery-standard → build-tester → code-review-optimizer → atlas-pre-push-review → cowork-git-push) has **not** fired. When the build phase begins, the kicker is `atlas-delivery-standard` (TCL setup) before any code lands. Document this session as the prerequisite design pass, not as Atlas dev work itself.

---

## How to use this handoff

- Paste the **Resolved decisions** table into the mempalace task thread as the headline.
- Paste the **Final document set** table to give pointers to the canonical files.
- Paste the **Pre-build checklist** when Matt is ready to start the build phase.
- Keep the **Still open** table on the side; it's the agenda for the next design round when Matt has answers.

End of handoff doc.
