"""Help Desk + Provisioning benchmark executors for Sprint 27 stage 9."""

from __future__ import annotations

import json

from .helpdesk_simulation import (
    HelpDeskScenario,
    HelpDeskSimulationEngine,
    helpdesk_dashboard_payload,
)
from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner


def register_helpdesk_executors(runner: BenchmarkRunner) -> None:
    """Register deterministic Help Desk Lab probes."""

    runner.register_executor("helpdesk.ticket_generation", _ticket_generation)
    runner.register_executor("helpdesk.baseline_vs_atlas", _baseline_vs_atlas)
    runner.register_executor("helpdesk.first_response", _first_response)
    runner.register_executor("helpdesk.automation_coverage", _automation_coverage)
    runner.register_executor("helpdesk.provisioning", _provisioning)
    runner.register_executor("helpdesk.workload_capacity", _workload_capacity)
    runner.register_executor("helpdesk.scale", _scale)
    runner.register_executor("helpdesk.frontend_contract", _frontend_contract)


def _scenario(case: BenchmarkCase) -> HelpDeskScenario:
    raw = case.parameters.get("scenario", case.parameters)
    if not isinstance(raw, dict):
        raise ValueError("scenario parameters must be an object")
    return HelpDeskScenario.from_dict(raw)


def _metrics(result) -> dict[str, float | int | str | bool]:
    scenario = result.scenario
    return {
        "simulation.synthetic": True,
        "simulation.guaranteed_savings": False,
        "simulation.sla_guaranteed": False,
        "simulation.atlas_time_source": scenario.atlas_time_source,
        "tickets": scenario.tickets_per_period,
        "technicians": scenario.technician_count,
        "managed_devices": scenario.managed_devices,
        "onboardings": scenario.onboardings_per_period,
        "ticket_automation_rate_pct": scenario.automation_rate_pct,
        "provisioning_automation_rate_pct": (
            scenario.provisioning_automation_rate_pct
        ),
        "manual_avg_first_response_minutes": (
            result.manual_avg_first_response_minutes
        ),
        "atlas_avg_first_response_minutes": result.atlas_avg_first_response_minutes,
        "first_response_reduction_pct": result.first_response_reduction_pct,
        "manual_expected_escalations": result.manual_expected_escalations,
        "atlas_expected_escalations": result.atlas_expected_escalations,
        "manual_provisioning_human_hours": result.manual_provisioning_human_hours,
        "atlas_provisioning_human_hours": result.atlas_provisioning_human_hours,
        "provisioning_elapsed_reduction_pct": (
            result.provisioning_elapsed_reduction_pct
        ),
        "manual_human_hours": result.total_manual_human_hours,
        "atlas_human_hours": result.total_atlas_human_hours,
        "human_hours_liberated": result.human_hours_liberated,
        "human_time_reduction_pct": result.human_time_reduction_pct,
        "manual_operations_per_human_hour": result.manual_operations_per_human_hour,
        "atlas_operations_per_human_hour": result.atlas_operations_per_human_hour,
        "potential_capacity_value_brl": result.potential_capacity_value_brl,
    }


def _ticket_generation(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    scenario = _scenario(case)
    requested = int(case.parameters.get("sample_count", scenario.tickets_per_period))
    tickets = HelpDeskSimulationEngine.generate_tickets(
        scenario,
        seed=context.case_seed,
        count=requested,
    )
    unique_ids = len({ticket.ticket_id for ticket in tickets})
    valid_categories = all(
        ticket.category in scenario.ticket_categories for ticket in tickets
    )
    synthetic_ids = all(ticket.ticket_id.startswith("HD-SIM-") for ticket in tickets)
    passed = (
        len(tickets) == requested
        and unique_ids == requested
        and valid_categories
        and synthetic_ids
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "generated_tickets": len(tickets),
            "unique_ticket_ids": unique_ids,
            "category_count": len({ticket.category for ticket in tickets}),
            "remote_eligible_tickets": sum(
                ticket.remote_eligible for ticket in tickets
            ),
            "privacy.synthetic_identifiers_only": synthetic_ids,
        },
        details=("Synthetic tickets contain no real employee or customer data.",),
    )


def _baseline_vs_atlas(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = HelpDeskSimulationEngine().simulate(_scenario(case))
    arithmetic_ok = abs(
        result.human_hours_liberated
        - (result.total_manual_human_hours - result.total_atlas_human_hours)
    ) <= 0.002
    return CaseOutcome(
        status=BenchmarkStatus.PASS if arithmetic_ok else BenchmarkStatus.FAIL,
        score=100.0 if arithmetic_ok else 0.0,
        metrics=_metrics(result),
        details=(
            "Workload comparison is synthetic and does not assume staff reduction.",
        ),
    )


def _first_response(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = HelpDeskSimulationEngine().simulate(_scenario(case))
    passed = (
        result.manual_avg_first_response_minutes >= 0
        and result.atlas_avg_first_response_minutes >= 0
        and 0 <= result.first_response_reduction_pct <= 100
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=_metrics(result),
        details=("Response values are weighted by the automation assumption.",),
    )


def _automation_coverage(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = HelpDeskSimulationEngine().simulate(_scenario(case))
    passed = (
        result.manual_expected_escalations >= 0
        and result.atlas_expected_escalations >= 0
        and result.ticket_business.automated_items >= 0
        and result.ticket_business.manual_items_remaining >= 0
    )
    metrics = _metrics(result)
    metrics.update(
        {
            "automated_tickets": result.ticket_business.automated_items,
            "manual_tickets_remaining": result.ticket_business.manual_items_remaining,
            "manual_expected_errors": result.ticket_business.manual_expected_errors,
            "atlas_expected_errors": result.ticket_business.atlas_expected_errors,
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=("Escalation and error values are scenario assumptions.",),
    )


def _provisioning(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = HelpDeskSimulationEngine().simulate(_scenario(case))
    passed = (
        result.manual_provisioning_human_hours >= 0
        and result.atlas_provisioning_human_hours >= 0
        and result.atlas_provisioning_machine_hours >= 0
        and 0 <= result.provisioning_elapsed_reduction_pct <= 100
    )
    metrics = _metrics(result)
    metrics.update(
        {
            "manual_avg_provisioning_elapsed_minutes": (
                result.manual_avg_provisioning_elapsed_minutes
            ),
            "atlas_avg_provisioning_elapsed_minutes": (
                result.atlas_avg_provisioning_elapsed_minutes
            ),
            "atlas_provisioning_machine_hours": (
                result.atlas_provisioning_machine_hours
            ),
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=(
            "Provisioning is simulated in dry-run terms; no workstation is modified.",
        ),
    )


def _workload_capacity(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    result = HelpDeskSimulationEngine().simulate(_scenario(case))
    passed = (
        result.total_manual_human_hours >= 0
        and result.total_atlas_human_hours >= 0
        and result.manual_operations_per_human_hour >= 0
        and result.atlas_operations_per_human_hour >= 0
    )
    metrics = _metrics(result)
    metrics.update(
        {
            "manual_utilization_pct": result.manual_utilization_pct,
            "atlas_human_utilization_pct": result.atlas_human_utilization_pct,
            "annual_potential_capacity_value_brl": (
                result.annual_potential_capacity_value_brl
            ),
        }
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=("Capacity means reusable technician time, not layoffs.",),
    )


def _scale(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    raw_volumes = case.parameters.get("volumes", [100, 500, 1200])
    if not isinstance(raw_volumes, list) or not raw_volumes:
        raise ValueError("volumes must be a non-empty list")
    volumes = [int(value) for value in raw_volumes]
    if any(value <= 0 for value in volumes):
        raise ValueError("all volumes must be positive")

    raw_scenario = case.parameters.get("scenario", {})
    if not isinstance(raw_scenario, dict):
        raise ValueError("scenario parameters must be an object")
    base_tickets = int(raw_scenario.get("tickets_per_period", 1200))
    base_onboardings = int(raw_scenario.get("onboardings_per_period", 15))
    onboarding_ratio = base_onboardings / base_tickets if base_tickets else 0.0

    engine = HelpDeskSimulationEngine()
    reductions: list[float] = []
    for volume in volumes:
        payload = dict(raw_scenario)
        payload["tickets_per_period"] = volume
        payload["onboardings_per_period"] = max(
            0,
            round(volume * onboarding_ratio),
        )
        result = engine.simulate(HelpDeskScenario.from_dict(payload))
        reductions.append(result.human_time_reduction_pct)

    max_delta = max(reductions) - min(reductions)
    passed = max_delta <= 1.0
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "simulation.synthetic": True,
            "volume_levels": len(volumes),
            "min_tickets": min(volumes),
            "max_tickets": max(volumes),
            "human_time_reduction_pct_min": min(reductions),
            "human_time_reduction_pct_max": max(reductions),
            "reduction_pct_delta": round(max_delta, 3),
        },
        details=("Help Desk assumptions remain stable across scaled volume.",),
    )


def _frontend_contract(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    result = HelpDeskSimulationEngine().simulate(_scenario(case))
    payload = helpdesk_dashboard_payload(result)
    output = context.scratch_dir / "helpdesk-dashboard.json"
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    restored = json.loads(output.read_text(encoding="utf-8"))
    checks = {
        "schema_version": restored.get("schema_version") == "1.0",
        "kind": restored.get("kind") == "helpdesk_provisioning_simulation",
        "response": isinstance(restored.get("response"), dict),
        "automation": isinstance(restored.get("automation"), dict),
        "provisioning": isinstance(restored.get("provisioning"), dict),
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
        details=("Help Desk payload is ready for the mini benchmark frontend.",),
    )
