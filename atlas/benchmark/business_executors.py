"""Business simulation benchmark executors for Sprint 27 stage 7."""

from __future__ import annotations

import json

from .business_presenter import dashboard_payload
from .business_simulation import BusinessScenario, BusinessSimulationEngine
from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner


def register_business_executors(runner: BenchmarkRunner) -> None:
    """Register transparent synthetic business simulation probes."""

    runner.register_executor("business.model_contract", _model_contract)
    runner.register_executor("business.baseline_vs_atlas", _baseline_vs_atlas)
    runner.register_executor("business.error_rework", _error_rework)
    runner.register_executor("business.capacity_projection", _capacity_projection)
    runner.register_executor("business.scale_consistency", _scale_consistency)
    runner.register_executor("business.frontend_contract", _frontend_contract)


def _scenario(case: BenchmarkCase) -> BusinessScenario:
    raw = case.parameters.get("scenario", case.parameters)
    if not isinstance(raw, dict):
        raise ValueError("scenario parameters must be an object")
    return BusinessScenario.from_dict(raw)


def _business_metrics(result) -> dict[str, float | int | str | bool]:
    scenario = result.scenario
    return {
        "simulation.synthetic": True,
        "simulation.guaranteed_savings": False,
        "simulation.atlas_time_source": scenario.atlas_time_source,
        "volume": scenario.volume_per_period,
        "staff_count": scenario.staff_count,
        "automation_rate_pct": scenario.automation_rate_pct,
        "manual_human_hours": result.manual_human_hours,
        "atlas_human_hours": result.atlas_human_hours,
        "atlas_machine_hours": result.atlas_machine_hours,
        "human_hours_liberated": result.human_hours_liberated,
        "human_time_reduction_pct": result.human_time_reduction_pct,
        "manual_expected_errors": result.manual_expected_errors,
        "atlas_expected_errors": result.atlas_expected_errors,
        "manual_capacity_items": result.manual_capacity_items,
        "atlas_capacity_items": result.atlas_capacity_items,
        "capacity_gain_pct": result.capacity_gain_pct,
        "potential_capacity_value_brl": result.potential_capacity_value_brl,
        "annual_potential_capacity_value_brl": (
            result.annual_potential_capacity_value_brl
        ),
    }


def _model_contract(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    scenario = _scenario(case)
    engine = BusinessSimulationEngine()
    result = engine.simulate(scenario)

    checks = {
        "synthetic_label": scenario.atlas_time_source == "synthetic_assumption",
        "volume_preserved": (
            result.automated_items + result.manual_items_remaining
            == scenario.volume_per_period
        ),
        "hours_nonnegative": (
            result.manual_human_hours >= 0 and result.atlas_human_hours >= 0
        ),
        "disclaimer_present": "not guaranteed" in engine.DISCLAIMER,
    }
    passed = sum(checks.values())
    score = passed / len(checks) * 100.0
    return CaseOutcome(
        status=(
            BenchmarkStatus.PASS if passed == len(checks) else BenchmarkStatus.FAIL
        ),
        score=round(score, 3),
        metrics={**checks, **_business_metrics(result)},
        details=(
            "PASS validates the simulation contract; it is not a commercial claim.",
        ),
    )


def _baseline_vs_atlas(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = BusinessSimulationEngine().simulate(_scenario(case))
    arithmetic_ok = (
        abs(
            result.human_hours_liberated
            - (result.manual_human_hours - result.atlas_human_hours)
        )
        <= 0.002
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if arithmetic_ok else BenchmarkStatus.FAIL,
        score=100.0 if arithmetic_ok else 0.0,
        metrics=_business_metrics(result),
        details=(
            "Manual and Atlas-assisted expected-value baselines were compared.",
        ),
    )


def _error_rework(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = BusinessSimulationEngine().simulate(_scenario(case))
    expected = (
        result.manual_expected_errors >= 0
        and result.atlas_expected_errors >= 0
        and result.manual_rework_hours >= 0
        and result.atlas_rework_hours >= 0
    )
    metrics = _business_metrics(result)
    metrics.update(
        {
            "manual_rework_hours": result.manual_rework_hours,
            "atlas_rework_hours": result.atlas_rework_hours,
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if expected else BenchmarkStatus.FAIL,
        score=100.0 if expected else 0.0,
        metrics=metrics,
        details=("Expected errors and rework are modeled explicitly.",),
    )


def _capacity_projection(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = BusinessSimulationEngine().simulate(_scenario(case))
    capacity_math_ok = (
        result.manual_capacity_items >= 0
        and result.atlas_capacity_items >= 0
        and result.available_human_hours > 0
    )
    metrics = _business_metrics(result)
    metrics.update(
        {
            "available_human_hours": result.available_human_hours,
            "manual_utilization_pct": result.manual_utilization_pct,
            "atlas_human_utilization_pct": result.atlas_human_utilization_pct,
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if capacity_math_ok else BenchmarkStatus.FAIL,
        score=100.0 if capacity_math_ok else 0.0,
        metrics=metrics,
        details=(
            "Capacity projection is based on human time per item, not layoffs.",
        ),
    )


def _scale_consistency(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    scenario = _scenario(case)
    raw_volumes = case.parameters.get("volumes", [100, 500, 2000])
    if not isinstance(raw_volumes, list) or not raw_volumes:
        raise ValueError("volumes must be a non-empty list")
    volumes = [int(value) for value in raw_volumes]
    if any(value <= 0 for value in volumes):
        raise ValueError("all volumes must be positive")

    engine = BusinessSimulationEngine()
    results = [engine.simulate(scenario.with_volume(volume)) for volume in volumes]
    reductions = [result.human_time_reduction_pct for result in results]
    baseline_reduction = reductions[0]
    max_delta = max(abs(value - baseline_reduction) for value in reductions)
    passed = max_delta <= 0.01

    metrics: dict[str, float | int | str | bool] = {
        "simulation.synthetic": True,
        "volume_levels": len(volumes),
        "min_volume": min(volumes),
        "max_volume": max(volumes),
        "reduction_pct_min": min(reductions),
        "reduction_pct_max": max(reductions),
        "reduction_pct_delta": round(max_delta, 3),
    }
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=(
            "Linear expected-value assumptions remain consistent across scale.",
        ),
    )


def _frontend_contract(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    result = BusinessSimulationEngine().simulate(_scenario(case))
    payload = dashboard_payload(result)
    output = context.scratch_dir / "business-dashboard.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    restored = json.loads(output.read_text(encoding="utf-8"))

    checks = {
        "schema_version": restored.get("schema_version") == "1.0",
        "business_kind": restored.get("kind") == "business_simulation",
        "comparison_present": isinstance(restored.get("comparison"), dict),
        "economics_present": isinstance(restored.get("economics"), dict),
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
            "frontend_ready": passed_count == len(checks),
            "dashboard_schema_version": "1.0",
            "dashboard_bytes": output.stat().st_size,
            "simulation.synthetic": True,
        },
        details=(
            "Dashboard payload contract is ready for the future mini frontend.",
        ),
    )
