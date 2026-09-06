"""Retail + Office benchmark executors for Sprint 27 stage 10."""

from __future__ import annotations

import json

from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .retail_office_simulation import (
    OfficeScenario,
    OfficeSimulationEngine,
    RetailScenario,
    RetailSimulationEngine,
    office_dashboard_payload,
    retail_dashboard_payload,
)
from .runner import BenchmarkContext, BenchmarkRunner


def register_retail_office_executors(runner: BenchmarkRunner) -> None:
    runner.register_executor("retail.event_generation", _retail_event_generation)
    runner.register_executor("retail.baseline_vs_atlas", _retail_baseline_vs_atlas)
    runner.register_executor("retail.exception_response", _retail_exception_response)
    runner.register_executor("retail.scale", _retail_scale)
    runner.register_executor("retail.frontend_contract", _retail_frontend_contract)
    runner.register_executor("office.task_generation", _office_task_generation)
    runner.register_executor("office.baseline_vs_atlas", _office_baseline_vs_atlas)
    runner.register_executor("office.turnaround", _office_turnaround)
    runner.register_executor("office.scale", _office_scale)
    runner.register_executor("office.frontend_contract", _office_frontend_contract)


def _retail_scenario(case: BenchmarkCase) -> RetailScenario:
    raw = case.parameters.get("scenario", case.parameters)
    if not isinstance(raw, dict):
        raise ValueError("scenario parameters must be an object")
    return RetailScenario.from_dict(raw)


def _office_scenario(case: BenchmarkCase) -> OfficeScenario:
    raw = case.parameters.get("scenario", case.parameters)
    if not isinstance(raw, dict):
        raise ValueError("scenario parameters must be an object")
    return OfficeScenario.from_dict(raw)


def _retail_metrics(result) -> dict[str, float | int | str | bool]:
    scenario = result.scenario
    business = result.business
    return {
        "simulation.synthetic": True,
        "simulation.guaranteed_savings": False,
        "simulation.atlas_time_source": scenario.atlas_time_source,
        "operations": scenario.operations_per_period,
        "staff": scenario.staff_count,
        "automation_rate_pct": scenario.automation_rate_pct,
        "manual_human_hours": business.manual_human_hours,
        "atlas_human_hours": business.atlas_human_hours,
        "human_hours_liberated": business.human_hours_liberated,
        "human_time_reduction_pct": business.human_time_reduction_pct,
        "exception_response_reduction_pct": result.exception_response_reduction_pct,
        "manual_operations_per_human_hour": result.manual_operations_per_human_hour,
        "atlas_operations_per_human_hour": result.atlas_operations_per_human_hour,
        "potential_capacity_value_brl": business.potential_capacity_value_brl,
    }


def _office_metrics(result) -> dict[str, float | int | str | bool]:
    scenario = result.scenario
    business = result.business
    return {
        "simulation.synthetic": True,
        "simulation.guaranteed_savings": False,
        "simulation.atlas_time_source": scenario.atlas_time_source,
        "tasks": scenario.tasks_per_period,
        "staff": scenario.staff_count,
        "automation_rate_pct": scenario.automation_rate_pct,
        "manual_human_hours": business.manual_human_hours,
        "atlas_human_hours": business.atlas_human_hours,
        "human_hours_liberated": business.human_hours_liberated,
        "human_time_reduction_pct": business.human_time_reduction_pct,
        "first_action_reduction_pct": result.first_action_reduction_pct,
        "manual_on_time_pct": result.manual_on_time_pct,
        "atlas_on_time_pct": result.atlas_on_time_pct,
        "manual_tasks_per_human_hour": result.manual_tasks_per_human_hour,
        "atlas_tasks_per_human_hour": result.atlas_tasks_per_human_hour,
        "potential_capacity_value_brl": business.potential_capacity_value_brl,
    }


def _retail_event_generation(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    scenario = _retail_scenario(case)
    requested = int(case.parameters.get("sample_count", scenario.operations_per_period))
    events = RetailSimulationEngine.generate_events(
        scenario,
        seed=context.case_seed,
        count=requested,
    )
    unique_ids = len({event.event_id for event in events})
    synthetic_ids = all(event.event_id.startswith("RT-SIM-") for event in events)
    valid_categories = all(event.category in scenario.categories for event in events)
    passed = len(events) == requested and unique_ids == requested and synthetic_ids and valid_categories
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "generated_events": len(events),
            "unique_event_ids": unique_ids,
            "high_priority_events": sum(event.priority == "high" for event in events),
            "privacy.synthetic_identifiers_only": synthetic_ids,
        },
        details=("Retail events are synthetic and contain no customer identifiers.",),
    )


def _retail_baseline_vs_atlas(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del context
    result = RetailSimulationEngine().simulate(_retail_scenario(case))
    business = result.business
    passed = business.manual_human_hours >= business.atlas_human_hours >= 0
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=_retail_metrics(result),
        details=("Retail workload values are synthetic operating assumptions.",),
    )


def _retail_exception_response(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del context
    result = RetailSimulationEngine().simulate(_retail_scenario(case))
    passed = (
        result.high_priority_operations >= 0
        and result.atlas_avg_exception_response_minutes >= 0
        and 0 <= result.exception_response_reduction_pct <= 100
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=_retail_metrics(result),
        details=("Exception response is a projection, not a guaranteed SLA.",),
    )


def _retail_scale(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del context
    raw_volumes = case.parameters.get("volumes", [250, 1000, 3000])
    if not isinstance(raw_volumes, list) or not raw_volumes:
        raise ValueError("volumes must be a non-empty list")
    volumes = [int(value) for value in raw_volumes]
    if any(value <= 0 for value in volumes):
        raise ValueError("all volumes must be positive")
    raw_scenario = case.parameters.get("scenario", {})
    if not isinstance(raw_scenario, dict):
        raise ValueError("scenario parameters must be an object")
    engine = RetailSimulationEngine()
    reductions: list[float] = []
    for volume in volumes:
        payload = dict(raw_scenario)
        payload["operations_per_period"] = volume
        reductions.append(
            engine.simulate(RetailScenario.from_dict(payload)).business.human_time_reduction_pct
        )
    delta = max(reductions) - min(reductions)
    passed = delta <= 1.0
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "volume_levels": len(volumes),
            "min_operations": min(volumes),
            "max_operations": max(volumes),
            "reduction_pct_delta": round(delta, 3),
        },
        details=("Retail assumptions remain stable across scaled volume.",),
    )


def _retail_frontend_contract(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    payload = retail_dashboard_payload(RetailSimulationEngine().simulate(_retail_scenario(case)))
    output = context.scratch_dir / "retail-dashboard.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    restored = json.loads(output.read_text(encoding="utf-8"))
    checks = {
        "schema_version": restored.get("schema_version") == "1.0",
        "kind": restored.get("kind") == "retail_simulation",
        "exceptions": isinstance(restored.get("exceptions"), dict),
        "workload": isinstance(restored.get("workload"), dict),
        "economics": isinstance(restored.get("economics"), dict),
        "frontend": isinstance(restored.get("frontend"), dict),
        "disclaimer": bool(restored.get("disclaimer")),
    }
    passed_count = sum(checks.values())
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == len(checks) else BenchmarkStatus.FAIL,
        score=round(passed_count / len(checks) * 100.0, 3),
        metrics={
            **checks,
            "frontend_ready": passed_count == len(checks),
            "dashboard_schema_version": "1.0",
            "dashboard_bytes": output.stat().st_size,
            "simulation.synthetic": True,
        },
        details=("Retail payload is ready for the mini benchmark frontend.",),
    )


def _office_task_generation(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    scenario = _office_scenario(case)
    requested = int(case.parameters.get("sample_count", scenario.tasks_per_period))
    tasks = OfficeSimulationEngine.generate_tasks(
        scenario,
        seed=context.case_seed,
        count=requested,
    )
    unique_ids = len({task.task_id for task in tasks})
    synthetic_ids = all(task.task_id.startswith("OF-SIM-") for task in tasks)
    valid_categories = all(task.category in scenario.categories for task in tasks)
    passed = len(tasks) == requested and unique_ids == requested and synthetic_ids and valid_categories
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "generated_tasks": len(tasks),
            "unique_task_ids": unique_ids,
            "priority_tasks": sum(task.urgency == "priority" for task in tasks),
            "privacy.synthetic_identifiers_only": synthetic_ids,
        },
        details=("Office tasks are synthetic and contain no real employee data.",),
    )


def _office_baseline_vs_atlas(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del context
    result = OfficeSimulationEngine().simulate(_office_scenario(case))
    business = result.business
    passed = business.manual_human_hours >= business.atlas_human_hours >= 0
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=_office_metrics(result),
        details=("Office workload values are synthetic operating assumptions.",),
    )


def _office_turnaround(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del context
    result = OfficeSimulationEngine().simulate(_office_scenario(case))
    passed = (
        0 <= result.first_action_reduction_pct <= 100
        and 0 <= result.manual_on_time_pct <= 100
        and 0 <= result.atlas_on_time_pct <= 100
        and result.atlas_on_time_tasks >= result.manual_on_time_tasks
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=_office_metrics(result),
        details=("Turnaround and deadline coverage are synthetic projections.",),
    )


def _office_scale(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del context
    raw_volumes = case.parameters.get("volumes", [200, 800, 1800])
    if not isinstance(raw_volumes, list) or not raw_volumes:
        raise ValueError("volumes must be a non-empty list")
    volumes = [int(value) for value in raw_volumes]
    if any(value <= 0 for value in volumes):
        raise ValueError("all volumes must be positive")
    raw_scenario = case.parameters.get("scenario", {})
    if not isinstance(raw_scenario, dict):
        raise ValueError("scenario parameters must be an object")
    engine = OfficeSimulationEngine()
    reductions: list[float] = []
    for volume in volumes:
        payload = dict(raw_scenario)
        payload["tasks_per_period"] = volume
        reductions.append(
            engine.simulate(OfficeScenario.from_dict(payload)).business.human_time_reduction_pct
        )
    delta = max(reductions) - min(reductions)
    passed = delta <= 1.0
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "volume_levels": len(volumes),
            "min_tasks": min(volumes),
            "max_tasks": max(volumes),
            "reduction_pct_delta": round(delta, 3),
        },
        details=("Office assumptions remain stable across scaled volume.",),
    )


def _office_frontend_contract(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    payload = office_dashboard_payload(OfficeSimulationEngine().simulate(_office_scenario(case)))
    output = context.scratch_dir / "office-dashboard.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    restored = json.loads(output.read_text(encoding="utf-8"))
    checks = {
        "schema_version": restored.get("schema_version") == "1.0",
        "kind": restored.get("kind") == "office_simulation",
        "turnaround": isinstance(restored.get("turnaround"), dict),
        "deadlines": isinstance(restored.get("deadlines"), dict),
        "workload": isinstance(restored.get("workload"), dict),
        "frontend": isinstance(restored.get("frontend"), dict),
        "disclaimer": bool(restored.get("disclaimer")),
    }
    passed_count = sum(checks.values())
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == len(checks) else BenchmarkStatus.FAIL,
        score=round(passed_count / len(checks) * 100.0, 3),
        metrics={
            **checks,
            "frontend_ready": passed_count == len(checks),
            "dashboard_schema_version": "1.0",
            "dashboard_bytes": output.stat().st_size,
            "simulation.synthetic": True,
        },
        details=("Office payload is ready for the mini benchmark frontend.",),
    )
