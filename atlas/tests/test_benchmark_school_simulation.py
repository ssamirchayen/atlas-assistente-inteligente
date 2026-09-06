from __future__ import annotations

import pytest

from atlas.benchmark.school_simulation import (
    SchoolLeadScenario,
    SchoolLeadSimulationEngine,
    school_dashboard_payload,
)


def _scenario(**overrides) -> SchoolLeadScenario:
    payload = {
        "scenario_id": "test.school",
        "title": "Test School",
        "leads_per_period": 2000,
        "consultant_count": 5,
        "work_hours_per_consultant": 176,
        "hourly_cost_brl": 20,
        "courses": ("Radiologia", "Enfermagem"),
        "sources": ("Instagram", "WhatsApp"),
        "after_hours_lead_pct": 30,
        "automation_rate_pct": 80,
        "manual_first_response_business_minutes": 35,
        "manual_after_hours_wait_minutes": 600,
        "atlas_first_response_seconds": 8,
        "manual_response_handling_minutes": 2,
        "manual_qualification_minutes": 3,
        "manual_crm_minutes": 2,
        "followups_per_lead": 2,
        "manual_followup_minutes": 2,
        "manual_followup_coverage_pct": 65,
        "atlas_followup_coverage_pct": 98,
        "atlas_processing_seconds_per_automated_lead": 18,
        "human_review_minutes_per_automated_lead": 0.5,
        "manual_error_rate_pct": 4,
        "atlas_error_rate_pct": 1,
        "rework_minutes_per_error": 5,
    }
    payload.update(overrides)
    return SchoolLeadScenario(**payload)


def test_school_scenario_rejects_invalid_percentage():
    with pytest.raises(ValueError, match="automation_rate_pct"):
        _scenario(automation_rate_pct=110)


def test_manual_minutes_include_expected_followup_work():
    scenario = _scenario(
        manual_response_handling_minutes=2,
        manual_qualification_minutes=3,
        manual_crm_minutes=2,
        followups_per_lead=2,
        manual_followup_minutes=2,
        manual_followup_coverage_pct=50,
    )

    assert scenario.manual_minutes_per_lead == 9.0


def test_school_engine_reduces_response_time_when_automation_is_enabled():
    result = SchoolLeadSimulationEngine().simulate(_scenario())

    assert result.atlas_avg_first_response_minutes < (
        result.manual_avg_first_response_minutes
    )
    assert result.first_response_reduction_pct > 0


def test_school_engine_keeps_followup_coverage_bounded():
    result = SchoolLeadSimulationEngine().simulate(_scenario())

    assert 0 <= result.manual_followup_coverage_pct <= 100
    assert 0 <= result.atlas_followup_coverage_pct <= 100


def test_synthetic_leads_are_deterministic_and_privacy_safe():
    scenario = _scenario(leads_per_period=20)
    engine = SchoolLeadSimulationEngine()

    first = engine.generate_leads(scenario, seed=27)
    second = engine.generate_leads(scenario, seed=27)

    assert first == second
    assert len(first) == 20
    assert len({lead.lead_id for lead in first}) == 20
    assert all(lead.lead_id.startswith("SIM-") for lead in first)


def test_school_dashboard_payload_is_frontend_ready():
    result = SchoolLeadSimulationEngine().simulate(_scenario())
    payload = school_dashboard_payload(result)

    assert payload["schema_version"] == "1.0"
    assert payload["kind"] == "school_lead_simulation"
    assert "response" in payload
    assert "followups" in payload
    assert "workload" in payload
    assert "frontend" in payload
    assert payload["quality"]["conversion_modeled"] is False
    assert "does not guarantee" in payload["disclaimer"]
