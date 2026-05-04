"""KG extraction transaction log — cost telemetry + anomaly detection.

version: 0.1
phase: kg-auto-extract

Purpose
-------
Records every call to kg_extractor.extract_triples() in a SQLite table so the
operator can:
  - See total spend over any time window (`mempalace kg-backfill --stats`)
  - Detect anomalies (a single drawer that cost 10x more than usual, a runaway
    backfill, etc.) so a buggy prompt doesn't silently spiral cost.
  - Audit which drawers got extracted, when, by what process, with what result.

Storage
-------
SQLite, default at `<palace_dir>/kg_extract_log.sqlite3` so it lives next to
the KG database itself (operator can grep one folder for everything KG-related).

Cost calculation
----------------
Public Anthropic pricing for Haiku 4.5 (as of 2026-05): $0.80/M input tokens,
$4.00/M output tokens. Override via env:
  MEMPALACE_KG_PRICE_INPUT_PER_M    (default 0.80)
  MEMPALACE_KG_PRICE_OUTPUT_PER_M   (default 4.00)

Anomaly detection
-----------------
A call is flagged anomalous if EITHER:
  - cost_usd > MEMPALACE_KG_COST_ABSOLUTE_CEILING (default $0.50 per call),
  - or cost_usd > 3 * p95(cost over last `WINDOW_CALLS` successful calls).

Flagging is informational — the call still succeeds and the triples still
land. The flag goes into the log row + a WARNING log line so a `grep flagged`
in container logs surfaces them.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional

logger = logging.getLogger("mempalace.kg_extract_log")


# ── Cost rates (env-tunable) ─────────────────────────────────────────────────

def _price_input_per_m() -> float:
    return float(os.environ.get("MEMPALACE_KG_PRICE_INPUT_PER_M", "0.80"))


def _price_output_per_m() -> float:
    return float(os.environ.get("MEMPALACE_KG_PRICE_OUTPUT_PER_M", "4.00"))


def _cost_absolute_ceiling() -> float:
    return float(os.environ.get("MEMPALACE_KG_COST_ABSOLUTE_CEILING", "0.50"))


# Number of recent calls used for the p95 baseline. Small enough to react to
# real prompt changes; large enough to be statistically meaningful.
WINDOW_CALLS = 50

# Multiplier over p95 that triggers the anomaly flag.
ANOMALY_MULTIPLIER = 3.0


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Compute USD cost for a call given token counts. Pure, no I/O."""
    in_cost = (input_tokens / 1_000_000.0) * _price_input_per_m()
    out_cost = (output_tokens / 1_000_000.0) * _price_output_per_m()
    return round(in_cost + out_cost, 6)


# ── DB schema ───────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_extract_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    drawer_id TEXT,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    input_cost_usd REAL NOT NULL DEFAULT 0.0,
    output_cost_usd REAL NOT NULL DEFAULT 0.0,
    total_cost_usd REAL NOT NULL DEFAULT 0.0,
    triples_extracted INTEGER NOT NULL DEFAULT 0,
    novel_predicates INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT,
    flagged_anomaly TEXT
);
CREATE INDEX IF NOT EXISTS idx_kg_log_timestamp ON kg_extract_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_kg_log_source ON kg_extract_log(source);
CREATE INDEX IF NOT EXISTS idx_kg_log_status ON kg_extract_log(status);
"""


# ── ExtractLog (the public interface) ────────────────────────────────────────

class ExtractLog:
    """Append-only SQLite log of extraction calls.

    Single instance per process is fine; SQLite handles concurrent writes
    from a single process via internal locking.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = self._default_db_path()
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @staticmethod
    def _default_db_path() -> str:
        # Co-locate with KG database under the palace dir.
        palace = os.environ.get("MEMPAL_PALACE_PATH")
        if palace:
            return str(Path(palace).expanduser() / "kg_extract_log.sqlite3")
        # Fallback to ~/.mempalace
        home = Path(os.environ.get("HOME", os.path.expanduser("~")))
        return str(home / ".mempalace" / "kg_extract_log.sqlite3")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── Recording ───────────────────────────────────────────────────────────

    def record(
        self,
        *,
        source: str,
        model: str,
        status: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        triples_extracted: int = 0,
        novel_predicates: int = 0,
        duration_ms: int = 0,
        drawer_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """Append one row. Returns the row id. Always succeeds (best-effort).

        Anomaly detection runs INSIDE this method — if the call's cost is
        above the absolute ceiling or above 3x p95 of recent successful
        calls, the row is tagged with the reason and a WARNING is logged.
        """
        in_cost = (input_tokens / 1_000_000.0) * _price_input_per_m()
        out_cost = (output_tokens / 1_000_000.0) * _price_output_per_m()
        total_cost = round(in_cost + out_cost, 6)

        flag = self._anomaly_reason(total_cost) if status == "success" else None
        if flag:
            logger.warning(
                "kg_extract_log: anomalous cost %.6f USD on %s (drawer=%s) — %s",
                total_cost, source, drawer_id, flag,
            )

        row_id = str(uuid.uuid4())
        try:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO kg_extract_log (
                        id, timestamp, source, drawer_id, model,
                        input_tokens, output_tokens,
                        input_cost_usd, output_cost_usd, total_cost_usd,
                        triples_extracted, novel_predicates, duration_ms,
                        status, error_message, flagged_anomaly
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id, datetime.utcnow().isoformat(timespec="seconds") + "Z",
                        source, drawer_id, model,
                        input_tokens, output_tokens,
                        round(in_cost, 6), round(out_cost, 6), total_cost,
                        triples_extracted, novel_predicates, duration_ms,
                        status, error_message, flag,
                    ),
                )
        except sqlite3.Error as exc:
            # Log-failure must not bubble up — extraction itself succeeded.
            logger.exception("kg_extract_log: write failed: %s", exc)

        return row_id

    # ── Anomaly detection ───────────────────────────────────────────────────

    def _anomaly_reason(self, cost_usd: float) -> Optional[str]:
        """Return a human-readable reason if `cost_usd` is anomalous, else None."""
        ceiling = _cost_absolute_ceiling()
        if cost_usd > ceiling:
            return f"cost ${cost_usd:.4f} exceeds absolute ceiling ${ceiling:.4f}"

        p95 = self._recent_p95_cost()
        if p95 is not None and cost_usd > ANOMALY_MULTIPLIER * p95:
            return (
                f"cost ${cost_usd:.4f} exceeds {ANOMALY_MULTIPLIER}x p95 "
                f"(${p95:.4f}) of last {WINDOW_CALLS} successful calls"
            )
        return None

    def _recent_p95_cost(self) -> Optional[float]:
        """p95 of total_cost_usd for the last WINDOW_CALLS successful calls.
        Returns None if fewer than 10 baseline calls (not enough signal yet).
        """
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """
                    SELECT total_cost_usd FROM kg_extract_log
                    WHERE status = 'success'
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (WINDOW_CALLS,),
                ).fetchall()
        except sqlite3.Error:
            return None
        if len(rows) < 10:
            return None
        costs = sorted(r["total_cost_usd"] for r in rows)
        idx = max(0, int(round(0.95 * (len(costs) - 1))))
        return costs[idx]

    # ── Reporting ───────────────────────────────────────────────────────────

    def summarize(
        self,
        *,
        window_days: Optional[int] = None,
        source: Optional[str] = None,
    ) -> dict:
        """Aggregate stats over a time window (or all-time if window_days is None).

        Returns:
            {
                "calls": total successful calls,
                "errors": failed calls,
                "skipped": skipped (no key, too short, etc.),
                "total_cost_usd": sum,
                "avg_cost_usd": mean of successful,
                "p50_cost_usd": median of successful,
                "p95_cost_usd": p95 of successful,
                "max_cost_usd": max of successful,
                "total_input_tokens": sum,
                "total_output_tokens": sum,
                "total_triples": sum,
                "total_novel_predicates": sum,
                "anomalies_flagged": count,
                "first_call": iso timestamp or None,
                "last_call": iso timestamp or None,
            }
        """
        where = ["1=1"]
        params: list = []
        if window_days is not None:
            cutoff = (
                datetime.utcnow().timestamp() - window_days * 86400
            )
            where.append("timestamp >= ?")
            params.append(
                datetime.utcfromtimestamp(cutoff).isoformat(timespec="seconds") + "Z"
            )
        if source is not None:
            where.append("source = ?")
            params.append(source)
        where_sql = " AND ".join(where)

        with self._conn() as conn:
            counts = conn.execute(
                f"""
                SELECT
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS calls,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS errors,
                    SUM(CASE WHEN status NOT IN ('success', 'error') THEN 1 ELSE 0 END) AS skipped,
                    SUM(total_cost_usd) AS total_cost_usd,
                    SUM(input_tokens) AS total_input_tokens,
                    SUM(output_tokens) AS total_output_tokens,
                    SUM(triples_extracted) AS total_triples,
                    SUM(novel_predicates) AS total_novel_predicates,
                    SUM(CASE WHEN flagged_anomaly IS NOT NULL THEN 1 ELSE 0 END) AS anomalies_flagged,
                    MIN(timestamp) AS first_call,
                    MAX(timestamp) AS last_call
                FROM kg_extract_log
                WHERE {where_sql}
                """,
                params,
            ).fetchone()
            costs_rows = conn.execute(
                f"""
                SELECT total_cost_usd FROM kg_extract_log
                WHERE {where_sql} AND status = 'success'
                ORDER BY total_cost_usd
                """,
                params,
            ).fetchall()

        out = dict(counts) if counts else {}
        # SQLite SUM of empty set is None; coerce to 0/None as appropriate.
        for k in (
            "calls", "errors", "skipped",
            "total_input_tokens", "total_output_tokens",
            "total_triples", "total_novel_predicates", "anomalies_flagged",
        ):
            out[k] = int(out.get(k) or 0)
        out["total_cost_usd"] = float(out.get("total_cost_usd") or 0.0)

        costs = [r["total_cost_usd"] for r in costs_rows]
        if costs:
            out["avg_cost_usd"] = round(sum(costs) / len(costs), 6)
            out["p50_cost_usd"] = costs[len(costs) // 2]
            out["p95_cost_usd"] = costs[max(0, int(round(0.95 * (len(costs) - 1))))]
            out["max_cost_usd"] = costs[-1]
        else:
            out["avg_cost_usd"] = 0.0
            out["p50_cost_usd"] = 0.0
            out["p95_cost_usd"] = 0.0
            out["max_cost_usd"] = 0.0

        return out

    def recent_anomalies(self, limit: int = 20) -> List[dict]:
        """Most recent rows with flagged_anomaly set."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, source, drawer_id, total_cost_usd,
                       triples_extracted, flagged_anomaly
                FROM kg_extract_log
                WHERE flagged_anomaly IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Module-level convenience accessor ────────────────────────────────────────

_default_log: Optional[ExtractLog] = None


def get_default_log() -> ExtractLog:
    """Lazy singleton — most callers want the palace-co-located default log."""
    global _default_log
    if _default_log is None:
        _default_log = ExtractLog()
    return _default_log


def reset_default_log_for_tests() -> None:
    """Test-only: drop the cached singleton so a fresh path takes effect."""
    global _default_log
    _default_log = None
