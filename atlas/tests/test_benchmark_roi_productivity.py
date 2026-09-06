from __future__ import annotations

from pathlib import Path

import pytest

from atlas.benchmark.models import (
    BenchmarkKind,
    BenchmarkRun,
    BenchmarkSummary,
)
from atlas.benchmark.roi_productivity import (
    ProductivityEngine,
    ProductivitySnapshot,
    collect_measured_run_evidence,
    portfolio_dashboard_payload,
)
from atlas.benchmark.storage import BenchmarkRunStore


def _snapshot(**overrides) -> ProductivitySnapshot:
    payload = {
        "lab_id": "test",
        "title": "Test Lab",
        "period_label": "month",
        "volume": 1000.0,
        "automation_rate_pct": 75.0,
        "hourly_cost_brl": 20.0,
        "manual_human_hours": 100.0,
        "atlas_human_hours": 40.0,
        "manual_throughput_per_human_hour": 10.0,
        "atlas_throughput_per_human_hour": 25.0,
        "manual_expected_errors": 50.0,
        "atlas_expected_errors": 10.0,
        "manual_response_minutes": 20.0,
        "atlas_response_minutes": 5.0,
    }
    payload.update(overrides)
    return ProductivitySnapshot(**payload)


def test_productivity_math_is_transparent():
    result = ProductivityEngine().analyze(_snapshot())

    assert result.human_hours_liberated == 60.0
    assert result.human_time_reduction_pct == 60.0
    assert result.throughput_gain_pct == 150.0
    assert result.response_reduction_pct == 75.0
    assert result.expected_error_reduction_pct == 80.0
    assert result.human_intervention_rate_pct == 25.0


def test_economic_projection_uses_capacity_not_cash_savings_claim():
    result = ProductivityEngine().analyze(_snapshot())

    assert result.potential_capacity_value_brl == 1200.0
    assert result.annual_potential_capacity_value_brl == 14400.0


def test_portfolio_aggregates_labs_using_total_workload():
    engine = ProductivityEngine()
    portfolio = engine.consolidate(
        (
            _snapshot(lab_id="a", volume=1000),
            _snapshot(lab_id="b", volume=500),
        )
    )

    assert portfolio.total_volume == 1500.0
    assert portfolio.total_manual_human_hours == 200.0
    assert portfolio.total_atlas_human_hours == 80.0
    assert portfolio.total_human_hours_liberated == 120.0
    assert portfolio.human_time_reduction_pct == 60.0


def test_dashboard_keeps_provenance_separate():
    portfolio = ProductivityEngine().consolidate((_snapshot(),))
    payload = portfolio_dashboard_payload(portfolio)

    assert payload["evidence"]["measured"]["used_in_roi"] is False
    assert payload["evidence"]["simulated"]["used_in_roi"] is True
    assert payload["evidence"]["economic_projection"]["used_in_roi"] is True
    assert payload["frontend"]["ready"] is True
    assert "not a guarantee" in payload["disclaimer"]


def test_invalid_automation_rate_is_rejected():
    with pytest.raises(ValueError, match="automation_rate_pct"):
        _snapshot(automation_rate_pct=101.0)


def test_measured_history_collector_ignores_business_runs(tmp_path: Path):
    store = BenchmarkRunStore(tmp_path)
    summary = BenchmarkSummary(
        total=1,
        evaluated=1,
        passed=1,
        failed=0,
        errors=0,
        skipped=0,
        success_rate=100.0,
        weighted_score=100.0,
    )
    technical = BenchmarkRun(
        run_id="technical-run",
        suite_id="core",
        suite_title="Core",
        kind=BenchmarkKind.TECHNICAL,
        atlas_version="1.0.0",
        started_at_utc="2026-09-04T00:00:00Z",
        finished_at_utc="2026-09-04T00:00:01Z",
        seed=27,
        results=(),
        summary=summary,
    )
    business = BenchmarkRun(
        run_id="business-run",
        suite_id="school_leads",
        suite_title="School",
        kind=BenchmarkKind.BUSINESS_SIMULATION,
        atlas_version="1.0.0",
        started_at_utc="2026-09-04T00:00:00Z",
        finished_at_utc="2026-09-04T00:00:01Z",
        seed=27,
        results=(),
        summary=summary,
    )
    store.save(technical)
    store.save(business)

    evidence = collect_measured_run_evidence(tmp_path)

    assert len(evidence) == 1
    assert evidence[0].suite_id == "core"
