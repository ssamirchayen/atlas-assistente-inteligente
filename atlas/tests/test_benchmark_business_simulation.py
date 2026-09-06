from __future__ import annotations

import pytest

from atlas.benchmark.business_presenter import dashboard_payload
from atlas.benchmark.business_simulation import (
    BusinessScenario,
    BusinessSimulationEngine,
)


def _scenario(**overrides) -> BusinessScenario:
    payload = {
        "scenario_id": "test.business",
        "title": "Test Business",
        "volume_per_period": 1000,
        "staff_count": 5,
        "work_hours_per_staff": 176,
        "hourly_cost_brl": 20,
        "manual_minutes_per_item": 6,
        "atlas_seconds_per_automated_item": 15,
        "automation_rate_pct": 75,
        "human_review_minutes_per_automated_item": 0.5,
        "manual_error_rate_pct": 4,
        "atlas_error_rate_pct": 1,
        "rework_minutes_per_error": 5,
    }
    payload.update(overrides)
    return BusinessScenario(**payload)


def test_scenario_rejects_invalid_percentage():
    with pytest.raises(ValueError, match="automation_rate_pct"):
        _scenario(automation_rate_pct=101)


def test_manual_baseline_math_is_transparent():
    result = BusinessSimulationEngine().simulate(
        _scenario(automation_rate_pct=0, manual_error_rate_pct=0)
    )

    assert result.manual_human_hours == 100.0
    assert result.atlas_human_hours == 100.0
    assert result.human_hours_liberated == 0.0
    assert result.human_time_reduction_pct == 0.0


def test_full_automation_keeps_human_review_explicit():
    result = BusinessSimulationEngine().simulate(
        _scenario(
            volume_per_period=120,
            automation_rate_pct=100,
            human_review_minutes_per_automated_item=1,
            manual_error_rate_pct=0,
            atlas_error_rate_pct=0,
        )
    )

    assert result.atlas_human_hours == 2.0
    assert result.atlas_machine_hours == 0.5
    assert result.manual_items_remaining == 0.0


def test_error_rework_is_included_in_human_hours():
    result = BusinessSimulationEngine().simulate(
        _scenario(
            volume_per_period=100,
            automation_rate_pct=0,
            manual_error_rate_pct=10,
            rework_minutes_per_error=6,
        )
    )

    assert result.manual_rework_hours == 1.0
    assert result.manual_human_hours == 11.0


def test_annual_capacity_value_is_twelve_periods():
    result = BusinessSimulationEngine().simulate(_scenario())

    assert result.annual_potential_capacity_value_brl == pytest.approx(
        result.potential_capacity_value_brl * 12,
        abs=0.01,
    )


def test_scale_preserves_reduction_rate_for_linear_assumptions():
    engine = BusinessSimulationEngine()
    small = engine.simulate(_scenario(volume_per_period=100))
    large = engine.simulate(_scenario(volume_per_period=2000))

    assert small.human_time_reduction_pct == large.human_time_reduction_pct


def test_dashboard_payload_is_frontend_ready_and_disclaimed():
    result = BusinessSimulationEngine().simulate(_scenario())
    payload = dashboard_payload(result)

    assert payload["schema_version"] == "1.0"
    assert payload["kind"] == "business_simulation"
    assert "comparison" in payload
    assert "economics" in payload
    assert "not guaranteed" in payload["disclaimer"]


def test_with_volume_does_not_mutate_original_scenario():
    original = _scenario(volume_per_period=100)
    scaled = original.with_volume(500)

    assert original.volume_per_period == 100
    assert scaled.volume_per_period == 500
