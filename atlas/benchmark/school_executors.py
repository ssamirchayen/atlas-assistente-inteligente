"""School Lead Simulation benchmark executors for Sprint 27 stage 8."""

from __future__ import annotations

import json

from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner
from .school_simulation import (
    SchoolLeadScenario,
    SchoolLeadSimulationEngine,
    school_dashboard_payload,
)


def register_school_executors(runner: BenchmarkRunner) -> None:
    """Register deterministic School Lab probes."""

    runner.register_executor("school.lead_generation", _lead_generation)
    runner.register_executor("school.baseline_vs_atlas", _baseline_vs_atlas)
    runner.register_executor("school.first_response", _first_response)
    runner.register_executor("school.followup_coverage", _followup_coverage)
    runner.register_executor("school.workload_capacity", _workload_capacity)
    runner.register_executor("school.scale", _scale)
    runner.register_executor("school.frontend_contract", _frontend_contract)


def _scenario(case: BenchmarkCase) -> SchoolLeadScenario:
    raw = case.parameters.get("scenario", case.parameters)
    if not isinstance(raw, dict):
        raise ValueError("scenario parameters must be an object")
    return SchoolLeadScenario.from_dict(raw)


def _metrics(result) -> dict[str, float | int | str | bool]:
    scenario = result.scenario
    business = result.business
    return {
        "simulation.synthetic": True,
        "simulation.guaranteed_savings": False,
        "simulation.conversion_modeled": False,
        "simulation.atlas_time_source": scenario.atlas_time_source,
        "leads": scenario.leads_per_period,
        "consultants": scenario.consultant_count,
        "courses": len(scenario.courses),
        "after_hours_leads": result.after_hours_leads,
        "automation_rate_pct": scenario.automation_rate_pct,
        "manual_avg_first_response_minutes": (
            result.manual_avg_first_response_minutes
        ),
        "atlas_avg_first_response_minutes": result.atlas_avg_first_response_minutes,
        "first_response_reduction_pct": result.first_response_reduction_pct,
        "manual_followup_coverage_pct": result.manual_followup_coverage_pct,
        "atlas_followup_coverage_pct": result.atlas_followup_coverage_pct,
        "manual_human_hours": business.manual_human_hours,
        "atlas_human_hours": business.atlas_human_hours,
        "human_hours_liberated": business.human_hours_liberated,
        "human_time_reduction_pct": business.human_time_reduction_pct,
        "manual_leads_per_human_hour": result.manual_leads_per_human_hour,
        "atlas_leads_per_human_hour": result.atlas_leads_per_human_hour,
        "capacity_gain_pct": business.capacity_gain_pct,
        "potential_capacity_value_brl": business.potential_capacity_value_brl,
    }


def _lead_generation(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    scenario = _scenario(case)
    requested = int(case.parameters.get("sample_count", scenario.leads_per_period))
    leads = SchoolLeadSimulationEngine.generate_leads(
        scenario,
        seed=context.case_seed,
        count=requested,
    )
    unique_ids = len({lead.lead_id for lead in leads})
    valid_courses = all(lead.course in scenario.courses for lead in leads)
    valid_sources = all(lead.source in scenario.sources for lead in leads)
    no_personal_data = all(lead.lead_id.startswith("SIM-") for lead in leads)
    passed = (
        len(leads) == requested
        and unique_ids == requested
        and valid_courses
        and valid_sources
        and no_personal_data
    )
    after_hours_count = sum(lead.after_hours for lead in leads)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "generated_leads": len(leads),
            "unique_lead_ids": unique_ids,
            "course_count": len({lead.course for lead in leads}),
            "source_count": len({lead.source for lead in leads}),
            "after_hours_leads_generated": after_hours_count,
            "privacy.synthetic_identifiers_only": no_personal_data,
        },
        details=("Synthetic leads contain no real customer personal data.",),
    )


def _baseline_vs_atlas(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = SchoolLeadSimulationEngine().simulate(_scenario(case))
    business = result.business
    arithmetic_ok = abs(
        business.human_hours_liberated
        - (business.manual_human_hours - business.atlas_human_hours)
    ) <= 0.002
    return CaseOutcome(
        status=BenchmarkStatus.PASS if arithmetic_ok else BenchmarkStatus.FAIL,
        score=100.0 if arithmetic_ok else 0.0,
        metrics=_metrics(result),
        details=(
            "School workload comparison is synthetic and excludes conversion claims.",
        ),
    )


def _first_response(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = SchoolLeadSimulationEngine().simulate(_scenario(case))
    passed = (
        result.manual_avg_first_response_minutes >= 0
        and result.atlas_avg_first_response_minutes >= 0
        and result.first_response_reduction_pct <= 100.0
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=_metrics(result),
        details=("First-response values are weighted by after-hours assumptions.",),
    )


def _followup_coverage(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = SchoolLeadSimulationEngine().simulate(_scenario(case))
    passed = (
        0 <= result.manual_followup_coverage_pct <= 100
        and 0 <= result.atlas_followup_coverage_pct <= 100
        and result.manual_followups_completed >= 0
        and result.atlas_followups_completed >= 0
    )
    metrics = _metrics(result)
    metrics.update(
        {
            "manual_followups_completed": result.manual_followups_completed,
            "atlas_followups_completed": result.atlas_followups_completed,
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=("Follow-up coverage is a scenario assumption, not observed enrollment data.",),
    )


def _workload_capacity(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = SchoolLeadSimulationEngine().simulate(_scenario(case))
    business = result.business
    passed = (
        business.manual_human_hours >= 0
        and business.atlas_human_hours >= 0
        and result.manual_leads_per_human_hour >= 0
        and result.atlas_leads_per_human_hour >= 0
    )
    metrics = _metrics(result)
    metrics.update(
        {
            "available_human_hours": business.available_human_hours,
            "manual_utilization_pct": business.manual_utilization_pct,
            "atlas_human_utilization_pct": business.atlas_human_utilization_pct,
            "annual_potential_capacity_value_brl": (
                business.annual_potential_capacity_value_brl
            ),
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=("Capacity means reusable staff time, not assumed staff reduction.",),
    )


def _scale(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    raw_volumes = case.parameters.get("volumes", [100, 500, 2000])
    if not isinstance(raw_volumes, list) or not raw_volumes:
        raise ValueError("volumes must be a non-empty list")
    volumes = [int(value) for value in raw_volumes]
    if any(value <= 0 for value in volumes):
        raise ValueError("all volumes must be positive")

    engine = SchoolLeadSimulationEngine()
    reductions: list[float] = []
    for volume in volumes:
        payload = dict(case.parameters.get("scenario", {}))
        payload["leads_per_period"] = volume
        result = engine.simulate(SchoolLeadScenario.from_dict(payload))
        reductions.append(result.business.human_time_reduction_pct)

    max_delta = max(reductions) - min(reductions)
    passed = max_delta <= 0.01
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "volume_levels": len(volumes),
            "min_leads": min(volumes),
            "max_leads": max(volumes),
            "human_time_reduction_pct_min": min(reductions),
            "human_time_reduction_pct_max": max(reductions),
            "reduction_pct_delta": round(max_delta, 3),
        },
        details=("Linear School Lab assumptions remain stable across volume.",),
    )


def _frontend_contract(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    result = SchoolLeadSimulationEngine().simulate(_scenario(case))
    payload = school_dashboard_payload(result)
    output = context.scratch_dir / "school-dashboard.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    restored = json.loads(output.read_text(encoding="utf-8"))
    checks = {
        "schema_version": restored.get("schema_version") == "1.0",
        "kind": restored.get("kind") == "school_lead_simulation",
        "response": isinstance(restored.get("response"), dict),
        "followups": isinstance(restored.get("followups"), dict),
        "workload": isinstance(restored.get("workload"), dict),
        "frontend": isinstance(restored.get("frontend"), dict),
        "disclaimer": bool(restored.get("disclaimer")),
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
        details=("School Lab payload is ready for the mini benchmark frontend.",),
    )
