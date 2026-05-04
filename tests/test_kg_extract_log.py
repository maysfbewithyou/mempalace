"""Tests for the KG extraction transaction log.

version: 0.1
phase: kg-auto-extract
covers: mempalace.kg_extract_log (record / summarize / anomaly detection)
"""

from __future__ import annotations

import os
import tempfile

import pytest

from mempalace.kg_extract_log import (
    ANOMALY_MULTIPLIER,
    ExtractLog,
    estimate_cost_usd,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def log(tmp_path):
    """Fresh ExtractLog at a tmp DB path. Each test gets its own."""
    return ExtractLog(db_path=str(tmp_path / "log.sqlite3"))


# ── Cost math ────────────────────────────────────────────────────────────────


def test_estimate_cost_default_haiku_rates():
    # 1M in @ $0.80 + 1M out @ $4.00 = $4.80
    cost = estimate_cost_usd(1_000_000, 1_000_000)
    assert abs(cost - 4.80) < 1e-6


def test_estimate_cost_typical_drawer():
    # ~5 KB drawer, ~250 output tokens — roughly the per-call expectation.
    cost = estimate_cost_usd(1250, 250)
    assert 0.001 < cost < 0.005  # roughly $0.002


def test_estimate_cost_zero_inputs():
    assert estimate_cost_usd(0, 0) == 0.0


def test_estimate_cost_env_override(monkeypatch):
    monkeypatch.setenv("MEMPALACE_KG_PRICE_INPUT_PER_M", "1.60")
    monkeypatch.setenv("MEMPALACE_KG_PRICE_OUTPUT_PER_M", "8.00")
    # Doubled rates → doubled cost.
    cost = estimate_cost_usd(1_000_000, 1_000_000)
    assert abs(cost - 9.60) < 1e-6


# ── Recording basics ─────────────────────────────────────────────────────────


def test_record_success_call(log):
    row_id = log.record(
        source="tool_add_drawer",
        model="claude-haiku-4-5-20251001",
        status="success",
        input_tokens=1250,
        output_tokens=300,
        triples_extracted=4,
        novel_predicates=1,
        duration_ms=1100,
        drawer_id="drawer_xyz",
    )
    assert row_id  # non-empty UUID

    stats = log.summarize()
    assert stats["calls"] == 1
    assert stats["errors"] == 0
    assert stats["total_triples"] == 4
    assert stats["total_novel_predicates"] == 1
    assert stats["total_input_tokens"] == 1250
    assert stats["total_output_tokens"] == 300
    assert stats["total_cost_usd"] > 0


def test_record_error_call_does_not_affect_success_stats(log):
    log.record(source="tool_add_drawer", model="m", status="error",
               error_message="API down")
    log.record(source="tool_add_drawer", model="m", status="success",
               input_tokens=100, output_tokens=50, triples_extracted=2)
    stats = log.summarize()
    assert stats["calls"] == 1  # only successes count toward "calls"
    assert stats["errors"] == 1
    assert stats["total_triples"] == 2


def test_record_skipped_status(log):
    """no_api_key / too_short paths use a non-success non-error status."""
    log.record(source="tool_add_drawer", model="m", status="no_api_key")
    log.record(source="tool_add_drawer", model="m", status="too_short")
    stats = log.summarize()
    assert stats["calls"] == 0
    assert stats["errors"] == 0
    assert stats["skipped"] == 2


# ── Anomaly detection ────────────────────────────────────────────────────────


def test_anomaly_above_absolute_ceiling(log, monkeypatch):
    """A single huge call gets flagged even with no baseline."""
    monkeypatch.setenv("MEMPALACE_KG_COST_ABSOLUTE_CEILING", "0.50")
    log.record(source="kg-backfill", model="m", status="success",
               input_tokens=1_000_000, output_tokens=500_000)
    anomalies = log.recent_anomalies()
    assert len(anomalies) == 1
    assert "exceeds absolute ceiling" in anomalies[0]["flagged_anomaly"]


def test_no_anomaly_under_absolute_ceiling(log, monkeypatch):
    monkeypatch.setenv("MEMPALACE_KG_COST_ABSOLUTE_CEILING", "0.50")
    log.record(source="kg-backfill", model="m", status="success",
               input_tokens=1000, output_tokens=200)
    assert log.recent_anomalies() == []


def test_anomaly_above_p95_multiplier(log, monkeypatch):
    """Need 10+ baseline calls; then a call >3x p95 of the baseline flags."""
    # Set ceiling well above all test costs so only the p95 rule fires.
    monkeypatch.setenv("MEMPALACE_KG_COST_ABSOLUTE_CEILING", "100.0")

    # Seed 12 cheap baseline calls (~$0.0008 each).
    for _ in range(12):
        log.record(source="tool_add_drawer", model="m", status="success",
                   input_tokens=1000, output_tokens=0)

    # Now a 100x-cost call: should flag against p95.
    log.record(source="tool_add_drawer", model="m", status="success",
               input_tokens=100_000, output_tokens=0)
    anomalies = log.recent_anomalies()
    assert len(anomalies) >= 1
    assert "p95" in anomalies[0]["flagged_anomaly"]


def test_p95_baseline_silent_below_min_baseline(log, monkeypatch):
    """With <10 baseline calls, p95 detection does nothing (avoids noise on
    a fresh deployment)."""
    monkeypatch.setenv("MEMPALACE_KG_COST_ABSOLUTE_CEILING", "100.0")
    # Only 5 baseline calls.
    for _ in range(5):
        log.record(source="tool_add_drawer", model="m", status="success",
                   input_tokens=1000, output_tokens=0)
    # A 100x call should still NOT flag because we don't have enough baseline.
    log.record(source="tool_add_drawer", model="m", status="success",
               input_tokens=100_000, output_tokens=0)
    assert log.recent_anomalies() == []


# ── Summarize windowing ──────────────────────────────────────────────────────


def test_summarize_filter_by_source(log):
    log.record(source="tool_add_drawer", model="m", status="success",
               input_tokens=100, output_tokens=50, triples_extracted=1)
    log.record(source="kg-backfill", model="m", status="success",
               input_tokens=200, output_tokens=100, triples_extracted=5)
    add_stats = log.summarize(source="tool_add_drawer")
    backfill_stats = log.summarize(source="kg-backfill")
    assert add_stats["calls"] == 1 and add_stats["total_triples"] == 1
    assert backfill_stats["calls"] == 1 and backfill_stats["total_triples"] == 5


def test_summarize_empty_log(log):
    """No calls yet — every total is zero, no exceptions."""
    stats = log.summarize()
    assert stats["calls"] == 0
    assert stats["errors"] == 0
    assert stats["total_cost_usd"] == 0.0
    assert stats["avg_cost_usd"] == 0.0
    assert stats["max_cost_usd"] == 0.0


def test_summarize_percentiles_with_real_data(log):
    """With 10+ successful calls, p50/p95/max should be sensible."""
    # 9 cheap calls + 1 expensive call.
    for _ in range(9):
        log.record(source="t", model="m", status="success",
                   input_tokens=1000, output_tokens=200)
    log.record(source="t", model="m", status="success",
               input_tokens=10_000, output_tokens=2000)

    stats = log.summarize()
    assert stats["calls"] == 10
    assert stats["p50_cost_usd"] < stats["max_cost_usd"]
    assert stats["max_cost_usd"] >= stats["p95_cost_usd"]
    # The single expensive call drives max ~10x higher than p50.
    assert stats["max_cost_usd"] > stats["p50_cost_usd"] * 5
