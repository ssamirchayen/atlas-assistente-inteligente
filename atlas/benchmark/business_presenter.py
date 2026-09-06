"""Frontend-ready presentation contract for business simulation results."""

from __future__ import annotations

from .business_simulation import BusinessSimulationEngine, BusinessSimulationResult


def dashboard_payload(result: BusinessSimulationResult) -> dict[str, object]:
    """Return a stable JSON-safe payload for the future mini benchmark UI."""

    scenario = result.scenario
    return {
        "schema_version": "1.0",
        "kind": "business_simulation",
        "scenario": {
            "id": scenario.scenario_id,
            "title": scenario.title,
            "period": scenario.period_label,
            "volume": scenario.volume_per_period,
            "staff_count": scenario.staff_count,
            "atlas_time_source": scenario.atlas_time_source,
        },
        "comparison": {
            "manual_human_hours": result.manual_human_hours,
            "atlas_human_hours": result.atlas_human_hours,
            "atlas_machine_hours": result.atlas_machine_hours,
            "human_hours_liberated": result.human_hours_liberated,
            "human_time_reduction_pct": result.human_time_reduction_pct,
            "capacity_gain_pct": result.capacity_gain_pct,
        },
        "operations": {
            "automated_items": result.automated_items,
            "manual_items_remaining": result.manual_items_remaining,
            "manual_expected_errors": result.manual_expected_errors,
            "atlas_expected_errors": result.atlas_expected_errors,
        },
        "economics": {
            "potential_capacity_value_brl": result.potential_capacity_value_brl,
            "annual_potential_capacity_value_brl": (
                result.annual_potential_capacity_value_brl
            ),
        },
        "disclaimer": BusinessSimulationEngine.DISCLAIMER,
    }
