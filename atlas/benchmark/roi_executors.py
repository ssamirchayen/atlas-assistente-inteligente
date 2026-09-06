"""Benchmark executors for Sprint 27 stage 11 ROI + Productivity Engine."""

from __future__ import annotations

import json
from pathlib import Path

from .catalog import BenchmarkCatalog
from .helpdesk_simulation import HelpDeskScenario, HelpDeskSimulationEngine
from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .retail_office_simulation import (
    OfficeScenario,
    OfficeSimulationEngine,
    RetailScenario,
    RetailSimulationEngine,
)
from .roi_productivity import (
    ProductivityEngine,
    ProductivitySnapshot,
    collect_measured_run_evidence,
    helpdesk_snapshot,
    office_snapshot,
    portfolio_dashboard_payload,
    retail_snapshot,
    school_snapshot,
)
from .runner import BenchmarkContext, BenchmarkRunner
from .school_simulation import SchoolLeadScenario, SchoolLeadSimulationEngine


def register_roi_productivity_executors(runner: BenchmarkRunner) -> None:
    runner.register_executor("roi.lab_normalization", _lab_normalization)
    runner.register_executor("roi.productivity_math", _productivity_math)
    runner.register_executor("roi.economic_projection", _economic_projection)
    runner.register_executor("roi.provenance_separation", _provenance_separation)
    runner.register_executor("roi.measured_history", _measured_history)
    runner.register_executor("roi.sensitivity", _sensitivity)
    runner.register_executor("roi.frontend_contract", _frontend_contract)


def _case_scenario(
    project_root: Path,
    suite_id: str,
    case_id: str,
) -> dict[str, object]:
    catalog = BenchmarkCatalog(project_root / "benchmarks" / "suites")
    suite = catalog.get(suite_id)
    case = next((item for item in suite.cases if item.case_id == case_id), None)
    if case is None:
        raise ValueError(f"case not found: {suite_id}/{case_id}")
    raw = case.parameters.get("scenario")
    if not isinstance(raw, dict):
        raise ValueError(f"scenario missing: {suite_id}/{case_id}")
    return dict(raw)


def _snapshots(project_root: Path) -> tuple[ProductivitySnapshot, ...]:
    school_scenario = SchoolLeadScenario.from_dict(
        _case_scenario(project_root, "school_leads", "school.baseline_vs_atlas")
    )
    school_result = SchoolLeadSimulationEngine().simulate(school_scenario)

    helpdesk_scenario = HelpDeskScenario.from_dict(
        _case_scenario(
            project_root,
            "helpdesk_provisioning",
            "helpdesk.baseline_vs_atlas",
        )
    )
    helpdesk_result = HelpDeskSimulationEngine().simulate(helpdesk_scenario)

    retail_scenario = RetailScenario.from_dict(
        _case_scenario(project_root, "retail_office", "retail.baseline_vs_atlas")
    )
    retail_result = RetailSimulationEngine().simulate(retail_scenario)

    office_scenario = OfficeScenario.from_dict(
        _case_scenario(project_root, "retail_office", "office.baseline_vs_atlas")
    )
    office_result = OfficeSimulationEngine().simulate(office_scenario)

    return (
        school_snapshot(school_result),
        helpdesk_snapshot(helpdesk_result),
        retail_snapshot(retail_result),
        office_snapshot(office_result),
    )


def _portfolio(context: BenchmarkContext):
    return ProductivityEngine().consolidate(_snapshots(context.project_root))


def _base_metrics(portfolio) -> dict[str, float | int | str | bool]:
    return {
        "simulation.synthetic": True,
        "roi.commercial_guarantee": False,
        "labs": len(portfolio.labs),
        "total_volume": portfolio.total_volume,
        "manual_human_hours": portfolio.total_manual_human_hours,
        "atlas_human_hours": portfolio.total_atlas_human_hours,
        "human_hours_liberated": portfolio.total_human_hours_liberated,
        "human_time_reduction_pct": portfolio.human_time_reduction_pct,
        "throughput_gain_pct": portfolio.throughput_gain_pct,
        "weighted_automation_rate_pct": portfolio.weighted_automation_rate_pct,
        "human_intervention_rate_pct": (
            portfolio.weighted_human_intervention_rate_pct
        ),
        "potential_capacity_value_brl": portfolio.potential_capacity_value_brl,
        "annual_potential_capacity_value_brl": (
            portfolio.annual_potential_capacity_value_brl
        ),
    }


def _lab_normalization(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    snapshots = _snapshots(context.project_root)
    lab_ids = tuple(item.lab_id for item in snapshots)
    expected = ("school", "helpdesk", "retail", "office")
    passed = lab_ids == expected and all(item.volume > 0 for item in snapshots)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "lab_count": len(snapshots),
            "school_volume": snapshots[0].volume,
            "helpdesk_volume": snapshots[1].volume,
            "retail_volume": snapshots[2].volume,
            "office_volume": snapshots[3].volume,
        },
        details=("Four prior business labs normalize to one productivity contract.",),
    )


def _productivity_math(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    portfolio = _portfolio(context)
    passed = (
        portfolio.total_manual_human_hours > 0
        and portfolio.total_atlas_human_hours > 0
        and portfolio.total_human_hours_liberated > 0
        and portfolio.atlas_throughput_per_human_hour
        > portfolio.manual_throughput_per_human_hour
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=_base_metrics(portfolio),
        details=(
            "Portfolio productivity is aggregated from synthetic workload metrics.",
        ),
    )


def _economic_projection(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    portfolio = _portfolio(context)
    expected_sum = round(
        sum(item.potential_capacity_value_brl for item in portfolio.labs),
        2,
    )
    expected_annual = round(
        sum(item.annual_potential_capacity_value_brl for item in portfolio.labs),
        2,
    )
    passed = (
        portfolio.potential_capacity_value_brl == expected_sum
        and portfolio.annual_potential_capacity_value_brl == expected_annual
        and expected_sum > 0
    )
    metrics = _base_metrics(portfolio)
    metrics.update(
        {
            "economics.provenance": "economic_projection",
            "economics.cash_savings_claim": False,
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=(
            "Economic values represent potential capacity, not guaranteed cash savings.",
        ),
    )


def _provenance_separation(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    portfolio = _portfolio(context)
    payload = portfolio_dashboard_payload(portfolio)
    evidence = payload["evidence"]
    measured = evidence["measured"]
    simulated = evidence["simulated"]
    projection = evidence["economic_projection"]
    checks = {
        "measured_not_used_in_roi": measured["used_in_roi"] is False,
        "simulated_used_in_roi": simulated["used_in_roi"] is True,
        "projection_used_in_roi": projection["used_in_roi"] is True,
        "disclaimer_present": bool(payload["disclaimer"]),
    }
    passed = all(checks.values())
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            **checks,
            "evidence.measured": "separate",
            "evidence.simulated": "operational_projection",
            "evidence.economic": "capacity_projection",
        },
        details=(
            "Measured technical evidence is never silently converted into ROI.",
        ),
    )


def _measured_history(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    max_runs = int(case.parameters.get("max_runs", 8))
    measured = collect_measured_run_evidence(
        context.project_root / "data" / "benchmark_runs",
        max_runs=max_runs,
    )
    passed = all(item.evaluated_cases >= 0 for item in measured)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "measured.available": bool(measured),
            "measured.technical_runs": len(measured),
            "measured.used_in_roi": False,
            "simulation.synthetic": True,
        },
        details=(
            "Technical history may be displayed, but absence of history is not a failure.",
        ),
    )


def _sensitivity(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    factor = float(case.parameters.get("hourly_cost_factor", 2.0))
    if factor <= 0:
        raise ValueError("hourly_cost_factor must be positive")
    snapshots = _snapshots(context.project_root)
    engine = ProductivityEngine()
    baseline = engine.consolidate(snapshots)
    scaled_snapshots = tuple(
        ProductivitySnapshot(
            lab_id=item.lab_id,
            title=item.title,
            period_label=item.period_label,
            volume=item.volume,
            automation_rate_pct=item.automation_rate_pct,
            hourly_cost_brl=item.hourly_cost_brl * factor,
            manual_human_hours=item.manual_human_hours,
            atlas_human_hours=item.atlas_human_hours,
            manual_throughput_per_human_hour=(
                item.manual_throughput_per_human_hour
            ),
            atlas_throughput_per_human_hour=item.atlas_throughput_per_human_hour,
            manual_expected_errors=item.manual_expected_errors,
            atlas_expected_errors=item.atlas_expected_errors,
            manual_response_minutes=item.manual_response_minutes,
            atlas_response_minutes=item.atlas_response_minutes,
            source=item.source,
        )
        for item in snapshots
    )
    scaled = engine.consolidate(scaled_snapshots)
    expected_value = baseline.potential_capacity_value_brl * factor
    operational_unchanged = (
        scaled.total_human_hours_liberated == baseline.total_human_hours_liberated
        and scaled.throughput_gain_pct == baseline.throughput_gain_pct
    )
    value_scaled = abs(scaled.potential_capacity_value_brl - expected_value) <= 0.05
    passed = operational_unchanged and value_scaled
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "hourly_cost_factor": factor,
            "operational_metrics_unchanged": operational_unchanged,
            "economic_projection_scaled": value_scaled,
            "baseline_capacity_value_brl": baseline.potential_capacity_value_brl,
            "scaled_capacity_value_brl": scaled.potential_capacity_value_brl,
        },
        details=(
            "Changing hourly cost changes economics only, not productivity math.",
        ),
    )


def _frontend_contract(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    max_runs = int(case.parameters.get("max_measured_runs", 8))
    portfolio = _portfolio(context)
    measured = collect_measured_run_evidence(
        context.project_root / "data" / "benchmark_runs",
        max_runs=max_runs,
    )
    payload = portfolio_dashboard_payload(portfolio, measured_runs=measured)
    output = context.scratch_dir / "roi-productivity-dashboard.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    restored = json.loads(output.read_text(encoding="utf-8"))
    checks = {
        "schema_version": restored.get("schema_version") == "1.0",
        "kind": restored.get("kind") == "roi_productivity_portfolio",
        "four_labs": len(restored.get("labs", [])) == 4,
        "evidence_present": isinstance(restored.get("evidence"), dict),
        "frontend_ready": restored.get("frontend", {}).get("ready") is True,
        "disclaimer_present": bool(restored.get("disclaimer")),
    }
    passed_count = sum(checks.values())
    return CaseOutcome(
        status=(
            BenchmarkStatus.PASS
            if passed_count == len(checks)
            else BenchmarkStatus.FAIL
        ),
        score=round(passed_count / len(checks) * 100.0, 3),
        metrics={
            **checks,
            "dashboard_bytes": output.stat().st_size,
            "dashboard_schema_version": "1.0",
            "frontend.tabs": 5,
        },
        details=(
            "Portfolio payload is ready for Sprint 27 stage 12 mini frontend.",
        ),
    )
