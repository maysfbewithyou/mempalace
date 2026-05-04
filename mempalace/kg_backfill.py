"""KG backfill — one-time / incremental extraction over existing drawers.

version: 0.1
phase: kg-auto-extract

Purpose
-------
The `tool_add_drawer` auto-extract hook (when MEMPALACE_KG_AUTO_EXTRACT=true)
catches every NEW drawer added via MCP. But the palace already contains ~1,636
drawers added before the hook existed. This module bulk-walks the existing
ChromaDB collection and runs the extractor on each drawer so the KG can be
populated retroactively.

CLI usage (registered in mempalace/cli.py as the `kg-backfill` subcommand):

    mempalace kg-backfill                 # prompt + run, all drawers
    mempalace kg-backfill --dry-run       # estimate cost, do nothing
    mempalace kg-backfill --limit 50      # only first 50
    mempalace kg-backfill --yes           # skip confirmation prompt
    mempalace kg-backfill --stats         # print log summary, no extraction

Cost discipline
---------------
1. Estimates cost BEFORE any API calls (assumes ~5 KB drawer × Haiku rates).
2. Prompts for confirmation unless --yes.
3. Records every call to kg_extract_log so totals + anomalies are tracked.
4. On Ctrl-C: stops cleanly between drawers (NOT mid-API-call) and prints
   partial-run stats.

Idempotency
-----------
Re-running backfill is safe. The KG's add_triple already de-dupes identical
(subject, predicate, object) where valid_to IS NULL. Re-extracting the same
drawer mostly produces the same triples and the dups get rejected at the KG
layer. Slight extra cost (the API call still ran), but no data corruption.

Output
------
Final summary printed to stdout with per-source breakdown. Detailed transaction
log queryable via ExtractLog.summarize() or `mempalace kg-backfill --stats`.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

from .kg_extract_log import (
    ExtractLog,
    estimate_cost_usd,
    get_default_log,
)
from .kg_extractor import (
    DEFAULT_MODEL,
    Triple,
    extract_triples,
)
from .knowledge_graph import KnowledgeGraph

logger = logging.getLogger("mempalace.kg_backfill")


# ── Cost estimation ─────────────────────────────────────────────────────────
# Per-drawer averages used to estimate the full-run cost BEFORE any API call.
# Real numbers will appear in kg_extract_log after the first batch of calls.

AVG_INPUT_TOKENS_PER_DRAWER = 1500   # ~6 KB drawer ≈ 1500 input tokens
AVG_OUTPUT_TOKENS_PER_DRAWER = 350   # JSON output, conservative


def estimate_full_run_cost(drawer_count: int) -> float:
    """Best-effort cost estimate for backfilling N drawers."""
    return estimate_cost_usd(
        AVG_INPUT_TOKENS_PER_DRAWER * drawer_count,
        AVG_OUTPUT_TOKENS_PER_DRAWER * drawer_count,
    )


# ── Drawer iteration ────────────────────────────────────────────────────────


def _iter_all_drawers(palace_path: Optional[str], limit: int = 0):
    """Yield (drawer_id, content, metadata) tuples for every drawer in the palace.

    palace_path: explicit override; if None, uses the env-configured default.
    limit: 0 means no limit; otherwise stop after this many drawers.
    """
    # Lazy import — palace.get_collection has heavy chromadb deps we don't want
    # to pay just by importing this module.
    from .palace import get_collection

    if palace_path is None:
        from .config import MempalaceConfig
        palace_path = MempalaceConfig().palace_path

    collection = get_collection(palace_path)
    if collection is None:
        raise RuntimeError(
            "kg_backfill: could not open chromadb collection at %s" % palace_path
        )

    # Pull in batches so we don't materialize the entire palace in memory.
    batch_size = 500
    offset = 0
    yielded = 0
    while True:
        batch = collection.get(
            limit=batch_size,
            offset=offset,
            include=["documents", "metadatas"],
        )
        ids = batch.get("ids", []) or []
        if not ids:
            break
        docs = batch.get("documents", []) or []
        metas = batch.get("metadatas", []) or []
        for i, drawer_id in enumerate(ids):
            content = docs[i] if i < len(docs) else ""
            meta = metas[i] if i < len(metas) else {}
            yield (drawer_id, content, meta or {})
            yielded += 1
            if limit and yielded >= limit:
                return
        offset += len(ids)
        if len(ids) < batch_size:
            break


# ── Main backfill driver ────────────────────────────────────────────────────


def run_backfill(
    *,
    palace_path: Optional[str] = None,
    dry_run: bool = False,
    limit: int = 0,
    yes: bool = False,
    kg: Optional[KnowledgeGraph] = None,
    extract_log: Optional[ExtractLog] = None,
) -> dict:
    """Walk all drawers, extract, write triples. Returns a summary dict.

    Parameters
    ----------
    palace_path : str, optional
        Override the default palace path.
    dry_run : bool
        Don't call the API, just count drawers and print cost estimate.
    limit : int
        Process at most this many drawers (0 = no limit).
    yes : bool
        Skip the confirmation prompt.
    kg : KnowledgeGraph, optional
        Override (for tests).
    extract_log : ExtractLog, optional
        Override (for tests).
    """
    log = extract_log or get_default_log()
    kg = kg or KnowledgeGraph()

    # ── Phase 1: count drawers + estimate cost ──────────────────────────────
    print("kg-backfill: scanning palace …", flush=True)
    drawer_count = 0
    for _ in _iter_all_drawers(palace_path, limit=limit):
        drawer_count += 1
    print(f"kg-backfill: found {drawer_count} drawer(s) to process", flush=True)
    if drawer_count == 0:
        return {"drawers_seen": 0, "triples_written": 0, "cost_usd": 0.0}

    cost_estimate = estimate_full_run_cost(drawer_count)
    print(
        f"kg-backfill: cost estimate ≈ ${cost_estimate:.4f} "
        f"using {DEFAULT_MODEL}",
        flush=True,
    )

    if dry_run:
        print("kg-backfill: --dry-run, nothing extracted", flush=True)
        return {
            "drawers_seen": drawer_count,
            "triples_written": 0,
            "cost_usd": 0.0,
            "estimated_cost_usd": cost_estimate,
            "dry_run": True,
        }

    if not yes:
        print(f"kg-backfill: proceed? Type 'yes' to continue: ", end="", flush=True)
        reply = sys.stdin.readline().strip().lower()
        if reply != "yes":
            print("kg-backfill: aborted.")
            return {"drawers_seen": drawer_count, "triples_written": 0, "cost_usd": 0.0, "aborted": True}

    # ── Phase 2: extract + persist ──────────────────────────────────────────
    started = time.monotonic()
    drawers_processed = 0
    triples_written = 0
    triples_failed = 0
    api_errors = 0
    skipped_short = 0

    try:
        for drawer_id, content, meta in _iter_all_drawers(palace_path, limit=limit):
            drawers_processed += 1
            try:
                triples = extract_triples(
                    content,
                    source="kg-backfill",
                    drawer_id=drawer_id,
                    extract_log=log,
                )
            except Exception:  # noqa: BLE001 — extract_triples is supposed to be safe
                logger.exception("kg_backfill: extract_triples raised on %s", drawer_id)
                api_errors += 1
                continue

            if not triples:
                skipped_short += 1
                continue

            for t in triples:
                try:
                    if t.subject_type:
                        kg.add_entity(t.subject, entity_type=t.subject_type)
                    if t.object_type:
                        kg.add_entity(t.object, entity_type=t.object_type)
                    kg.add_triple(
                        subject=t.subject,
                        predicate=t.predicate,
                        obj=t.object,
                        valid_from=t.valid_from,
                        valid_to=t.valid_to,
                        confidence=t.confidence,
                        source_file=f"drawer:{drawer_id}",
                    )
                    triples_written += 1
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "kg_backfill: failed to persist triple from %s", drawer_id,
                    )
                    triples_failed += 1

            # Progress every 25 drawers.
            if drawers_processed % 25 == 0:
                elapsed = time.monotonic() - started
                rate = drawers_processed / elapsed if elapsed else 0
                print(
                    f"kg-backfill: progress {drawers_processed}/{drawer_count} "
                    f"({rate:.1f}/s), {triples_written} triples written",
                    flush=True,
                )
    except KeyboardInterrupt:
        print("\nkg-backfill: interrupted; reporting partial stats", flush=True)

    # ── Phase 3: summary ────────────────────────────────────────────────────
    summary = log.summarize(source="kg-backfill")
    elapsed = time.monotonic() - started
    out = {
        "drawers_seen": drawer_count,
        "drawers_processed": drawers_processed,
        "triples_written": triples_written,
        "triples_failed": triples_failed,
        "api_errors": api_errors,
        "skipped_short": skipped_short,
        "elapsed_seconds": round(elapsed, 1),
        "cost_usd": summary["total_cost_usd"],
        "novel_predicates": summary["total_novel_predicates"],
        "anomalies_flagged": summary["anomalies_flagged"],
    }
    print("\nkg-backfill: complete")
    print(f"  drawers processed:    {out['drawers_processed']} of {out['drawers_seen']}")
    print(f"  triples written:      {out['triples_written']}")
    print(f"  triples failed:       {out['triples_failed']}")
    print(f"  api errors:           {out['api_errors']}")
    print(f"  skipped (too short):  {out['skipped_short']}")
    print(f"  novel predicates:     {out['novel_predicates']}")
    print(f"  anomalies flagged:    {out['anomalies_flagged']}")
    print(f"  cost USD:             ${out['cost_usd']:.4f}")
    print(f"  elapsed:              {out['elapsed_seconds']}s")
    return out


def print_stats(*, source: Optional[str] = None, window_days: Optional[int] = None) -> None:
    """Print kg_extract_log stats. Used by `mempalace kg-backfill --stats`."""
    log = get_default_log()
    summary = log.summarize(source=source, window_days=window_days)
    label = source or "all sources"
    window = f"last {window_days} day(s)" if window_days else "all time"
    print(f"kg_extract_log stats — {label} — {window}")
    print(f"  successful calls:   {summary['calls']}")
    print(f"  errors:             {summary['errors']}")
    print(f"  skipped:            {summary['skipped']}")
    print(f"  triples extracted:  {summary['total_triples']}")
    print(f"  novel predicates:   {summary['total_novel_predicates']}")
    print(f"  anomalies flagged:  {summary['anomalies_flagged']}")
    print(f"  total tokens (in):  {summary['total_input_tokens']:,}")
    print(f"  total tokens (out): {summary['total_output_tokens']:,}")
    print(f"  total cost USD:     ${summary['total_cost_usd']:.4f}")
    if summary["calls"]:
        print(f"  avg / call:         ${summary['avg_cost_usd']:.6f}")
        print(f"  p50 / p95 / max:    ${summary['p50_cost_usd']:.6f} / "
              f"${summary['p95_cost_usd']:.6f} / ${summary['max_cost_usd']:.6f}")
    if summary["first_call"]:
        print(f"  first call:         {summary['first_call']}")
        print(f"  last call:          {summary['last_call']}")
    anomalies = log.recent_anomalies(limit=10)
    if anomalies:
        print(f"\nrecent anomalies (last {len(anomalies)}):")
        for a in anomalies:
            drawer = a.get("drawer_id") or "(none)"
            print(
                f"  {a['timestamp']}  {a['source']:<18}  drawer={drawer:<40}  "
                f"${a['total_cost_usd']:.6f}  {a['flagged_anomaly']}"
            )
