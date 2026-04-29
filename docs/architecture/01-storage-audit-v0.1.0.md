# MemPalace Storage Audit
## Version 0.1.0 — April 2026

| Field | Value |
|---|---|
| Document | MemPalace Storage Audit |
| Version | v0.1.0 |
| Author | Cowork agent (read-only investigation) |
| Date | 2026-04-28 |
| Status | Draft for Matt's review |
| Companion docs | `ATLAS_DATABASE_GOVERNANCE_FRAMEWORK_v0.1.0.md`, `MemPalace_Phase_2_Architecture_v0.2.md`, `MemPalace_Deployment_Session_Log_v1.14.md`, `MemPalace_Deployment_Session_Log_v1.15.md` |
| Constraint | Read-only across all source. No code, schema, or migration changes proposed in this version. |

---

## 1. Executive summary

MemPalace's hosted deployment runs on a two-store stack inherited verbatim from the upstream `milla-jovovich/mempalace` project: **ChromaDB (PersistentClient, embedded) for vector drawers + a single SQLite file for the temporal knowledge graph** — both backed by one named Docker volume on `claude-brain.tstly.dev`. There is **zero** Postgres, alembic, SQLAlchemy, or psycopg in the package source; the IEP fork added only an HTTP wrapper, OAuth, and Docker plumbing on top of upstream's storage layer. We did not "spec the wrong thing" — we adopted upstream's design unchanged, and that design conflicts with Atlas Database Governance v0.1.0 in three concrete places (no migration chain, no RLS, no Three-Agent eligibility once the corpus crosses 50 records). My recommendation is **Path C — Hybrid (Chroma + Postgres)** as the v1 endgame, with **Path B (document the carve-out) as the v0.x interim** so Phase 4 mining is not blocked while the migration plan is built.

---

## 2. Current state — what's actually in the fork

### 2.1 Dependency pins (`pyproject.toml`)

The runtime dependency list, lines 28–31:

```toml
dependencies = [
    "chromadb>=0.5.23,<0.6",
    "pyyaml>=6.0.2,<7",
]
```

Optional `[http]` extra (lines 41–46) adds `starlette`, `uvicorn[standard]`, `pyjwt` — none of which touch storage. **No `psycopg`, `psycopg2`, `sqlalchemy`, `sqlmodel`, `asyncpg`, or `alembic` appears in `pyproject.toml`, in `mempalace/*.py`, or in any test fixture under `tests/`.** The matches that show up in a repo-wide grep for "Postgres" / "alembic" / "SQLAlchemy" are confined to:

- `README.md:13, 329, 331` — narrative claims about hypothetical user projects
- `benchmarks/BENCHMARKS.md:18, 192, 231` — synthetic benchmark text
- `tests/conftest.py:123` and `tests/benchmarks/data_generator.py:255, 268, 320` — fixture text used to fabricate fake conversations
- `_phase4_v010_full/*.md` — the Claude.ai conversation export staged for Phase 4 mining (these are *content*, not code)

In other words: the strings exist in the repo, but **never as imports, dependencies, or production-path code**.

### 2.2 The two stores in production code

#### Store A — ChromaDB (vector + drawers)

- Single point of truth: `mempalace/palace.py:8` `import chromadb`, `palace.py:37–46` `get_collection(palace_path, collection_name="mempalace_drawers")` calling `chromadb.PersistentClient(path=palace_path)`.
- Default collection name: `mempalace_drawers` (`config.py:62` `DEFAULT_COLLECTION_NAME = "mempalace_drawers"`).
- Default palace path: `~/.mempalace/palace` (`config.py:61` `DEFAULT_PALACE_PATH = os.path.expanduser("~/.mempalace/palace")`); container override `MEMPAL_PALACE_PATH=/data/.mempalace/palace` (`Dockerfile:71`, `docker-compose.coolify.yml:50`).
- `chromadb.PersistentClient(...)` is called from every storage-touching module: `palace.py:44`, `searcher.py:27, 101`, `palace_graph.py:27`, `miner.py:618`, `mcp_server.py:200`, `layers.py:94, 199, 263, 319, 440`, `cli.py:176, 266`. **No `HttpClient` or `EphemeralClient` anywhere** — Chroma is fully embedded in the same Python process as the wrapper child.
- ChromaDB telemetry is silenced at import time (`__init__.py:14`): `logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)`. Apple Silicon CoreML provider is force-disabled in `__init__.py:18–20` due to ONNX segfaults.

What lives in Chroma:
- **Drawers** — verbatim conversation/file content, the only "raw memory" surface. Written via `mempalace_add_drawer` / `mempalace mine`. Searched via `mempalace_search` and the L3 deep-search layer (`layers.py:261–321`).
- **Embeddings** for semantic search (default Chroma all-MiniLM-L6-v2, downloaded on first boot — see `Dockerfile:80–82` "ChromaDB's first-boot ONNX model download" healthcheck note).
- **Drawer metadata** — `wing`, `room`, `hall`, `source_file`, `source_mtime`, etc. — stored as Chroma collection metadata and used for the +34% wing/room filtering boost (`README.md:296–307`).

#### Store B — SQLite knowledge graph

- Single file: `~/.mempalace/knowledge_graph.sqlite3` (`knowledge_graph.py:46` `DEFAULT_KG_PATH = os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3")`).
- Connection setup: `knowledge_graph.py:91–96` opens with `sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)` and forces `PRAGMA journal_mode=WAL`.
- Schema is created inline by `_init_db()` at `knowledge_graph.py:55–88` via a single `executescript`:
  - `entities(id TEXT PK, name TEXT NOT NULL, type TEXT DEFAULT 'unknown', properties TEXT, created_at TEXT)`
  - `triples(id TEXT PK, subject TEXT, predicate TEXT, object TEXT, valid_from, valid_to, confidence REAL, source_closet, source_file, extracted_at, FK subject/object → entities.id)`
  - Three indexes: `idx_triples_subject`, `idx_triples_object`, `idx_triples_predicate`, `idx_triples_valid`.
- **There is no migration framework.** Schema is `CREATE TABLE IF NOT EXISTS …` evaluated on every cold start. Any change to the schema is a code edit in `knowledge_graph.py`; rollback is "git revert and hope nothing wrote to the new column."

What lives in SQLite:
- Temporal entity-relationship triples (Subject, Predicate, Object, valid_from, valid_to, confidence, source_closet, source_file).
- Used by `mempalace_kg_query`, `mempalace_kg_add`, `mempalace_kg_invalidate`, `mempalace_kg_timeline`, `mempalace_kg_stats` — five of the 19 MCP tools (`README.md:418–424`).

#### Store C — Plain JSON / text files in `~/.mempalace/`

- `~/.mempalace/config.json` — palace path, collection name, topic_wings, hall_keywords (`config.py:166–169`).
- `~/.mempalace/people_map.json` — name normalization (`config.py:174–180`).
- `~/.mempalace/identity.txt` — D9 Draft C identity, written on first boot by the wrapper (`http_server.py:139–149`).
- `~/.mempalace/wing_config.json` — wing keyword routing (referenced in `README.md:480–488`, written by `onboarding.py`).

These are not a "database" in the governance sense, but they hold authoritative state and are persisted on the same volume.

### 2.3 Deployment topology

Docker Compose (`docker-compose.coolify.yml`):

- **One service**: `mempalace-http` (`docker-compose.coolify.yml:23`). No Postgres service, no Chroma server, no Redis.
- **One named volume**: `mempalace_data` mounted at `/data` (`docker-compose.coolify.yml:64–66`, `volumes:` block lines 89–93). This single volume contains the ChromaDB persistent directory, the SQLite KG file, `config.json`, `identity.txt`, and the ONNX model cache.
- Host port: `5042:8000` (lines 56–62), routed through Cloudflare Tunnel as `claude-brain.tstly.dev` per the `cloudflared` route table on the Coolify host.
- Memory cap: 1 GB (line 87), single uvicorn worker (`Dockerfile:91–93`, "A4 — single worker is mandatory").

The architecture is intentionally single-process: the Starlette wrapper (`http_server.py:158–323`) spawns a long-lived child `python -m mempalace.mcp_server --palace /data/.mempalace/palace` (`http_server.py:124–132`) and proxies JSON-RPC over its stdin/stdout. Every read and write goes through that one child. **Concurrent requests are serialized via `asyncio.Lock`** (`http_server.py:172, 215`) because Chroma's PersistentClient and the SQLite KG are both single-writer-friendly only.

### 2.4 What the deployment session logs say

- **v1.14 (Phase 10 — OAuth complete, 2026-04-27)**: confirms the only deployed surface is `claude-brain.tstly.dev/mcp` plus OAuth metadata routes. No new storage primitives introduced; pyproject.toml change is `pyjwt` only (`v1.14.md:68`).
- **v1.15 (Phase 4 v0.1.0 staging, 2026-04-28)**: explicitly states the laptop CLI writes go to a *local* Chroma DB, not the hosted palace — *"Running `mempalace mine ... --mode convos` from the laptop CLI would write to a **local** Chroma DB at the configured `palace_path`, **not** the hosted palace at claude-brain.tstly.dev. That is also the wrong surface for Phase 4's 'hit the hosted palace' requirement."* (v1.15.md, "What was deliberately NOT done in this session"). This is the source of Matt's surprise.

### 2.5 So which of Matt's two hypotheses is right?

**Both, partially.** The ChromaDB came out-of-the-box from upstream and we never adapted it (his hypothesis #2 is correct on the facts). But upstream is also a *deliberate* design choice: a vector-first memory system is a normal application of Chroma, and the "96.6% LongMemEval R@5" headline number in `README.md:50–58` is achieved *because* of Chroma + its embedding model, not in spite of it. So we didn't spec the wrong tool for the *function*; we adopted a tool that doesn't fit the *governance regime* Atlas runs on. The mismatch is governance-shaped, not capability-shaped.

---

## 3. Comparison against Atlas Database Governance v0.1.0

| Governance section | Requirement | MemPalace status |
|---|---|---|
| §3 Database System Inventory | Every Atlas DB is named, owned, located, and stack-classified | **Missing.** MemPalace does not appear in the §3 table at all. Adding it requires picking a row label — "Self-hosted ChromaDB on Coolify" is not currently a recognized class. |
| §4 Migration naming & versioning | `NNN_verb_entity.sql` or `saNN_entity` chain with explicit `down_revision` | **Not honored.** No alembic, no migrations, no `down_revision`. Schema lives in `knowledge_graph.py:55–88` `executescript`. ChromaDB has no schema in the SQL sense — collection structure is implicit in the metadata dicts you write. |
| §5 Migration chain coordination | Fetch-before-add, replayable from any compatible head, slot-collision detection via `prescan.py` | **N/A — no migrations to coordinate.** The pre-push prescan SQL DDL grep would never trigger because there is no SQL DDL in the repo. |
| §6 Row-Level Security (RLS) | `ENABLE ROW LEVEL SECURITY` on every new table; role-gated writes via `auth.jwt() ->> 'role'` | **Cannot be honored on the current stack.** Neither Chroma nor SQLite supports RLS. Authorization happens at the HTTP layer (`http_server.py:339–386` `BearerAuthMiddleware` — static bearer or OAuth JWT). Inside the palace there is no per-row policy: any caller authenticated to `/mcp` can read any drawer / triple. |
| §7 Three-Agent Governance Model | Mandatory once corpus exceeds 50 records, holds time-varying data, and is used in workflows | **In scope, not implemented.** Phase 4 alone stages 67 conversations / 3,238 messages → after the first hosted ingest the palace will cross all three thresholds (`v1.15.md` "Staging results"). There is no Research / Integrity / Manager agent split, no Integrity Score, no weekly governance report. |
| §8 Schema change workflow | Up + down migration, never edit committed migration, prescan grep for DDL | **Not honored.** Schema changes to the KG are arbitrary `executescript` edits with no `up`/`down` artifact. |
| §9 Backup & Restore | Daily automated, restore-tested, 90-day retention, RTO ≤ 4 h, RPO ≤ 24 h | **Partial.** Coolify backs up the named volume `mempalace_data` if backup is configured for the project (`docker-compose.coolify.yml:91`). No restore-test runbook exists. RTO/RPO is undocumented. |
| §11 DB Access Matrix | Per-agent Postgres role, schema, RLS context | **Cannot be expressed.** No schemas, no roles. The matrix would need a "vector store carve-out" row: bearer/OAuth → entire palace, no sub-grants. |

Net read: out of 9 substantive governance sections, MemPalace honors **zero** as written. Some are inapplicable to a vector store (§4–§5 SQL migration chain, §8 DDL prescan); others (RLS §6, Three-Agent §7, Backup §9) Matt actually wants but the current stack doesn't support.

---

## 4. The three paths

### Path A — Migrate MemPalace to Postgres + pgvector

**What it looks like.** Rewrite `palace.py`, `searcher.py`, `layers.py`, `palace_graph.py`, `miner.py`, the L0–L3 layer code, and the KG to talk to a single Postgres instance with the `pgvector` extension. Drawers become a `palace.drawers` table with an `embedding vector(384)` column; the KG becomes `palace.entities` + `palace.triples`. Alembic owns the schema. Coolify gains a Postgres service in `docker-compose.coolify.yml`.

**Pros.**
- Honors §4, §5, §6, §7, §8, §9 of governance directly. RLS is real. Migrations are real. Backup is the same `pg_dump` Atlas core uses.
- One operational stack, one backup story, one access matrix row.
- pgvector is a Postgres extension — vector search lives in the same query plan as relational joins, so cross-store concerns disappear.
- Atlas team's existing Postgres familiarity transfers.

**Cons.**
- **High rewrite cost.** Twelve modules touch Chroma; eight touch SQLite. The MCP server (`mcp_server.py`) has 19 tools all built around the Chroma collection API. Estimate 3–5 weeks for a careful rewrite + test suite re-validation, plus the existing 85+ test suite needs the same migration.
- **Loss of upstream sync.** The IEP fork's stated D8 policy is monthly upstream sync (`http_server.py:166` "keeps upstream module untouched so monthly D8 sync stays clean"). Path A makes that policy non-viable — every upstream merge is a manual reconciliation against a divergent storage layer. The fork effectively *forks for real*.
- **Embedding model.** Chroma ships its ONNX MiniLM model out of the box. With pgvector you bring your own embedder — sentence-transformers in-process, an external service, or OpenAI's API. The "no API key, no cloud" promise of upstream needs a deliberate replacement.
- **Data migration.** Whatever's already in `claude-brain.tstly.dev`'s `mempalace_data` volume needs an export script. Today the volume is post-deploy + post-OAuth but pre-Phase-4-ingest, so this cost is currently low — and rises sharply once Phase 4 mining lands.
- **Benchmark risk.** The 96.6% LongMemEval result is benchmarked on Chroma + MiniLM. Switching the vector store and/or embedder requires re-running the benchmark to know whether quality is preserved.

### Path B — Keep ChromaDB, document it as a deliberate exception

**What it looks like.** No code changes. Atlas Database Governance v0.2.0 adds a "Vector & Memory Store Carve-Out" subsection to §3 and §11. MemPalace is recognized as a non-Postgres canonical store with a documented governance reduction: bearer/OAuth gates the entire palace, the Three-Agent model is replaced by a per-collection write log, and migrations are replaced by "schema lives in code, schema changes are part of the version bump."

**Pros.**
- **Zero rewrite cost.** Phase 4 mining proceeds today.
- Preserves clean upstream sync (D8 policy intact).
- Preserves the 96.6% benchmark posture without re-validation.
- Honest about the trade: governance is documented as reduced *and* the boundary is clear.

**Cons.**
- Two operational stacks forever. Two backup stories. Two restore runbooks. Two access matrices.
- §6 RLS does not exist for vector hits. If a future agent should see drawers from `wing_iep` but not `wing_personal`, that filtering is *application-layer only* — a bug in the wrapper bypasses it. With Postgres RLS, a bug in the wrapper *also* fails closed at the DB.
- Three-Agent model has to be reimagined. Research / Integrity / Manager all assume row-level proposals into a relational table. Translating that to "drawer proposals into a Chroma collection" is doable but the integrity score weights in §7.4 don't map (no "address verification" for a conversation drawer).
- The carve-out invites future debt: every new memory-style app the team builds has a precedent for "skip governance because vectors."

### Path C — Hybrid (ChromaDB for embeddings + Postgres for metadata/ACLs/audit)

**What it looks like.** ChromaDB stays as the pure vector store — embedding + ANN search only. Everything *about* a drawer (wing, room, hall, source_file, source_mtime, ingest_batch, who_added, agent_activity, audit history) and the entire KG move to Postgres. The MCP server's `_get_collection` (`mcp_server.py:204`) still talks to Chroma for the vector hit; it then joins to Postgres for metadata + ACL filtering before returning results. The Three-Agent governance applies to the Postgres half cleanly.

**Pros.**
- The Postgres side honors §4–§9 of governance directly.
- Three-Agent model has a natural home (proposals are rows in a Postgres `drawer_proposals` table; Manager Agent's approval flips a row into `drawers_metadata` and triggers the Chroma write).
- RLS over the metadata table gives wing-level read isolation for free.
- Audit log lives in Postgres next to Atlas core's existing audit conventions.
- Smaller rewrite than Path A: the SQLite KG (`knowledge_graph.py`) is the natural first target — its schema is already 2 tables, and there is *zero* upstream-sync penalty for moving it because the IEP fork is the only thing that uses the temporal validity layer in our context.
- The MemPalace investigation actually shows that **upstream is already a hybrid design** — Chroma + SQLite. Path C is "swap SQLite for Postgres, leave Chroma alone." That's a *much* smaller lift than the brief assumed.

**Cons.**
- Two stores to operate (same as B), but at least the *governable* half is in Atlas's Postgres world.
- Cross-store queries: filter-by-wing-then-vector-search needs either a Postgres pre-filter (id list) passed to Chroma, or a Chroma post-filter against a Postgres-supplied allowlist. Both are workable; both are awkward.
- Sync layer: when a drawer is added, the writes to Chroma and Postgres are not in the same transaction. Need an idempotent "Postgres-first, Chroma-second, retry-on-failure, reconcile-on-restart" pattern. Pattern is well-known but is real engineering.
- Upstream sync: Chroma reads/writes stay upstream-compatible; the KG diverges. A clean divergence (KG only, isolated module) is easier to maintain than Path A's whole-stack divergence.

---

## 5. Recommendation

**Adopt Path C as the v1 endgame. Adopt Path B as the v0.x interim — explicitly time-bounded.**

The trade-off I'm optimizing for: **let Phase 4 mining ship without delay AND end up at a stack that aligns with Atlas Database Governance, while preserving the 96.6% benchmark posture and the upstream-sync ergonomics that make the fork sustainable.**

Reasoning:

1. **Path A is too expensive for what it buys.** A full Postgres migration costs the team an upstream sync line (D8) and a re-benchmark cycle. The benefit — RLS over vectors — is not a problem we have today (single user, single tenant, bearer/OAuth at the door). It's a problem we have *eventually*, not now.

2. **Path B alone is sustainable but accumulates governance debt.** Documenting an exception is fine for one app. Doing it for every memory-shaped app the team builds is how we end up with three different "vector store carve-outs" in the Database Governance doc and no consistent answer.

3. **Path C is the smallest move that produces governance-aligned audit / RLS / Three-Agent eligibility.** The SQLite KG is already a relational store — moving it to Postgres is a clean, scoped migration, *not* a rewrite of the core memory system. The drawer metadata layer in Postgres gives RLS and Three-Agent eligibility for the data that needs governance most (which entities exist, who's connected to whom, who proposed what), while leaving the embedding layer where it's measurably good.

4. **Sequencing is what makes both viable.** v0.x = Path B with a deadline. v1.0 = Path C delivered.

### Implications for Phase 4 mining (currently staged)

- **Land the staged data on Chroma now**, exactly as v1.15 plans — Path B is in force during v0.x. The 67 staged conversation files in `_phase4_v010_full/` go through `mempalace_add_drawer` into the hosted palace's `mempalace_drawers` collection. Tag every drawer with `batch_id=phase-4-v0.1.0` and `source=claude-export` per v1.15's "Open items for Matt to resolve" item 1, so a later Postgres metadata table can backfill from Chroma metadata without ambiguity.
- **Do NOT seed the KG yet** beyond what the existing seed pattern produces. KG triples authored under the SQLite schema today will need a one-shot migration script to land on the Postgres schema later. Less seed = less migration cost.
- **Add a `phase4_audit.jsonl` line per drawer** to the volume during Phase 4 mining (one-line wrapper in the ingest call). This becomes the Path-C metadata bootstrap when we cut over.

### Governance updates that follow this recommendation

When Matt approves Path C as the endgame, Atlas Database Governance v0.2.0 needs:

- §3 Inventory: add a row "MemPalace Hosted (claude-brain.tstly.dev) — Self-hosted ChromaDB + Postgres metadata (Path C target) — Owner Matt — Status: Migrating Q3 2026."
- §3 Inventory: add a row "MemPalace Local (laptop CLI palaces) — Self-hosted ChromaDB + SQLite KG — Owner Matt — Status: Path B carve-out, not in scope for governance."
- New §13 (or §10.3) "Vector & Memory Store Carve-Out" — defines what governance looks like reduced for v0.x while Path C is in flight, and how it lifts when Path C lands.
- §11 Access Matrix: add MemPalace rows once Path C metadata schema is drafted.
- §7 Three-Agent: add MemPalace drawers to §7.7 once corpus crosses 50 records (immediately after Phase 4 lands).

---

## 6. Migration plan sketch — Path C (high level)

**Phase numbers below are NEW MemPalace phases, not Atlas dev phases.**

| Phase | Scope | Effort estimate | Risk |
|---|---|---|---|
| **MP-S1 — Postgres provisioning** | Stand up a `mempalace` Postgres on Coolify alongside the existing `mempalace-http` service. Define `palace.drawers_metadata`, `palace.entities`, `palace.triples`, `palace.audit_log`. Alembic chain `001_*` through `005_*` (project-local NNN convention per §4 Option A). Add the service to `docker-compose.coolify.yml`. | 3–5 days | Low. Standard Coolify Postgres provisioning. |
| **MP-S2 — KG cutover (SQLite → Postgres)** | Port `knowledge_graph.py` from `sqlite3` to `psycopg`/`SQLAlchemy`. Migration script: read every row from `~/.mempalace/knowledge_graph.sqlite3`, write to `palace.entities` + `palace.triples`. Re-run KG tests. | 1 week | Low–medium. KG schema is small (2 tables). |
| **MP-S3 — Drawer metadata mirror** | New write path: every `mempalace_add_drawer` call writes drawer body to Chroma AND a metadata row to `palace.drawers_metadata` (drawer_id, wing, room, hall, source_file, source_mtime, batch_id, added_by, added_at). Backfill from existing Chroma metadata. | 1 week | Medium. Two-write idempotency needs care. |
| **MP-S4 — RLS + Three-Agent enable** | Enable RLS on `palace.drawers_metadata`. Add agent roles per §11 of governance. Promote MemPalace to §7.7 of governance. Wire weekly governance report. | 3–5 days | Low. Pattern is already in the ROS Builder migrations. |
| **MP-S5 — Carve-out retirement** | Update Atlas Database Governance to v0.3.0 — remove the §13 carve-out for MemPalace Hosted. MemPalace Local laptop palaces stay carved-out indefinitely. | 1 day | None (doc-only). |

Total estimate: **3–4 weeks of focused work**, one engineer. Critical path is MP-S3 (two-write reconciliation pattern). Calendar: target landing Path C end of Q2 2026 / early Q3, after Phase 4 mining is complete and we have a stable corpus to migrate.

**Risks worth naming up front.**
- **Two-write atomicity.** A crash between the Chroma write and the Postgres metadata write produces an orphan in either store. Mitigate with: write Postgres FIRST (with `pending` status), THEN Chroma, THEN flip Postgres to `committed`. Reconcile-on-restart sweeps `pending` rows older than N seconds.
- **Read latency.** A search call now needs Chroma vector hit + Postgres metadata join. Both run in the same Coolify network; expected overhead is <10 ms. Validate before declaring done.
- **Embedding model lock-in.** This plan keeps Chroma + MiniLM. If we later want a different embedder (OpenAI text-embedding-3-small, BGE, etc.), that's a separate project and not blocked by this one.

---

## 7. Implications for Phase 4 mining

The staged content (`_phase4_v010_full/`, 67 files, 3,238 messages — `MemPalace_Deployment_Session_Log_v1.15.md` "Staging results") lands in **ChromaDB on the hosted palace** under Path B. Specifically:

- Drawer body → Chroma collection `mempalace_drawers` (the embedded PersistentClient at `/data/.mempalace/palace`).
- Drawer metadata (wing, room, hall, batch_id, source, ingested_at) → Chroma collection metadata, same row as the drawer.
- KG triples extracted from the conversations → SQLite at `/data/.mempalace/knowledge_graph.sqlite3` IF general extraction is enabled (`miner.py` general extractor path). Recommendation in §5 above is to **disable KG seeding for Phase 4** so we don't pay double migration cost — the conversations will still be searchable via Chroma; we re-derive KG triples post-Path-C cutover.
- Audit hook: I recommend adding a `phase4_audit.jsonl` write per ingest call (single line: `{drawer_id, batch_id, source, wing, ts}`) to the same `/data` volume. Cost is one extra `open(append)` per ingest. Benefit is a clean bootstrap for the Path-C metadata table.

This means the answer to "does Phase 4 land on Chroma or Postgres?" is unambiguously **Chroma only**, for now, by design — and the recommended Path-C migration treats the Phase 4 corpus as the canonical source-of-truth for drawer metadata when it backfills.

---

## 8. Open questions for Matt

1. **Endorse Path C as endgame, Path B as interim?** Or does the rewrite cost of Path A (single stack, full governance alignment from day one) feel worth it given that the corpus is small *right now*? A Path-A decision is cheaper today than after Phase 4 lands.

2. **KG cutover scope.** Path C's MP-S2 assumes the temporal-validity SQLite KG is worth carrying forward. Alternative: we drop the KG entirely and let Chroma metadata + a much simpler Postgres `entities` table cover the use case. This would shrink MP-S2 to ~1 day. Worth considering if KG triples aren't actually being authored in real-world use.

3. **Backup ground truth.** §9 of governance requires "automated daily backup with verified integrity." Coolify backs up `mempalace_data` *if backup is configured for the project* (`docker-compose.coolify.yml:91`). I do not know whether backup is currently enabled for the `claude-brain.tstly.dev` Coolify project. If not, Phase 4 mining is a §9 violation the moment the first drawer lands.

4. **Embedding-model commitment.** Chroma's default ONNX MiniLM is silently the embedder. Are we okay locking in MiniLM as the canonical embedder for the Atlas memory system, or do we want to call this an architectural decision Matt owns and document it under Path C?

5. **Local laptop palaces.** Matt runs `mempalace mine` from the laptop CLI. Each laptop is its own Chroma DB at `~/.mempalace/palace`. Are those *ever* in scope for governance, or is "local palace = personal tooling, hosted palace = canonical, ne'er the twain" the rule?

6. **Three-Agent for memory.** §7.4 of governance defines an Integrity Score with five components (Field Completeness, Address Verification, Duplicate Risk, Data Source Quality, Last Verified Recency). For drawer-shaped data — a verbatim conversation — "Address Verification" is meaningless. Does Matt want a memory-system Integrity Score variant (drop Address Verification, replace with something like Embedding Variance or Source Trust Tier), or do we exempt memory drawers from §7 entirely?

---

## 9. Suggested follow-up tasks

1. **Confirm Coolify volume backup status** for `mempalace_data` on `claude-brain.tstly.dev`. If off, turn it on before Phase 4 mining lands. (Owner: Matt, 30 min.)
2. **Draft Atlas Database Governance v0.2.0 §13 — Vector & Memory Store Carve-Out** as a 1-page subsection. (Owner: Cowork agent on Matt's signal, ~2 h.)
3. **Add `phase4_audit.jsonl` hook** to the Phase 4 ingest plan (v1.16 of the deployment session log). One-line append per `mempalace_add_drawer` call. Carries forward as Path-C bootstrap. (Owner: Cowork agent + Matt, ~1 h on top of Phase 4 ingest.)
4. **Build a Path-C feasibility spike** — a throwaway branch that adds a Postgres service to `docker-compose.coolify.yml` and proves the two-write idempotency pattern on a single test drawer. Confirms MP-S3 risk model before committing to the full migration. (Owner: Luke or Cowork agent, 1–2 days.)
5. **Re-run LongMemEval on the hosted palace post-Phase-4-ingest** before any Path-C work begins. We want a known-good benchmark on the corpus we'll be migrating. Currently the 96.6% number is upstream's; we don't have an IEP-fork-on-IEP-corpus number. (Owner: Matt or Cowork agent, ~2 h compute.)
6. **Decision-log this recommendation.** Whether Matt picks Path A, B, B-then-C, or "wait and revisit," capture the call as an entry in `MemPalace_Deployment_Session_Log_v1.16.md` so the rationale is preserved.

---

## Document Control

| Field | Value |
|---|---|
| Version | v0.1.0 |
| Effective Date | 2026-04-28 |
| Owner | Matt Brown |
| Reviewer | Luke (Engineering Lead) |
| Next Review | After Matt's decision on Path A/B/C, or end of Phase 4 mining — whichever first |
| Versioning | v0.x.y while recommendation is open. Bump to v1.0 on Matt's decision. |

### Version History

| Version | Date | Changes |
|---|---|---|
| v0.1.0 | 2026-04-28 | Initial baseline. Investigation triggered by Matt's question on Phase 4 mining ChromaDB reference. Read-only audit; no code/schema/migration changes. Recommendation: Path B (interim) → Path C (endgame). |

---

*MemPalace Storage Audit — Version 0.1.0*
*Status: draft for Matt's review. Read-only investigation; no production changes proposed.*
