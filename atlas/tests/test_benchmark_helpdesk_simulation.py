from __future__ import annotations

import pytest

from atlas.benchmark.helpdesk_simulation import (
    HelpDeskScenario,
    HelpDeskSimulationEngine,
    helpdesk_dashboard_payload,
)


def _scenario(**overrides) -> HelpDeskScenario:
    payload = {
        "scenario_id": "test.helpdesk",
        "title": "Test Help Desk",
        "tickets_per_period": 1200,
        "technician_count": 4,
        "work_hours_per_technician": 176,
        "hourly_cost_brl": 28,
        "managed_devices": 100,
        "onboardings_per_period": 15,
        "ticket_categories": (
            "password_access",
            "printing",
            "network",
            "slow_pc",
        ),
        "automation_rate_pct": 70,
        "manual_triage_minutes": 5,
        "manual_resolution_minutes": 22,
        "atlas_processing_seconds_per_automated_ticket": 45,
        "human_review_minutes_per_automated_ticket": 2,
        "manual_first_response_minutes": 18,
        "atlas_first_response_seconds": 10,
        "manual_error_rate_pct": 6,
        "atlas_error_rate_pct": 1.5,
        "rework_minutes_per_error": 12,
        "manual_escalation_rate_pct": 30,
        "atlas_escalation_rate_pct": 12,
        "manual_provisioning_minutes": 45,
        "atlas_provisioning_minutes": 8,
        "provisioning_automation_rate_pct": 80,
        "human_review_minutes_per_automated_provisioning": 3,
    }
    payload.update(overrides)
    return HelpDeskScenario(**payload)


def test_helpdesk_scenario_rejects_invalid_percentage():
    with pytest.raises(ValueError, match="automation_rate_pct"):
        _scenario(automation_rate_pct=101)


def test_manual_minutes_include_triage_and_resolution():
    scenario = _scenario(manual_triage_minutes=4, manual_resolution_minutes=16)

    assert scenario.manual_minutes_per_ticket == 20


def test_helpdesk_engine_reduces_first_response_with_automation():
    result = HelpDeskSimulationEngine().simulate(_scenario())

    assert result.atlas_avg_first_response_minutes < (
        result.manual_avg_first_response_minutes
    )
    assert result.first_response_reduction_pct > 0


def test_helpdesk_engine_combines_ticket_and_provisioning_workload():
    result = HelpDeskSimulationEngine().simulate(_scenario())

    assert result.total_manual_human_hours > result.ticket_business.manual_human_hours
    assert result.total_atlas_human_hours >= result.ticket_business.atlas_human_hours
    assert result.human_hours_liberated == pytest.approx(
        result.total_manual_human_hours - result.total_atlas_human_hours,
        abs=0.002,
    )


def test_synthetic_tickets_are_deterministic_and_privacy_safe():
    scenario = _scenario(tickets_per_period=25)
    engine = HelpDeskSimulationEngine()

    first = engine.generate_tickets(scenario, seed=27)
    second = engine.generate_tickets(scenario, seed=27)

    assert first == second
    assert len(first) == 25
    assert len({ticket.ticket_id for ticket in first}) == 25
    assert all(ticket.ticket_id.startswith("HD-SIM-") for ticket in first)


def test_helpdesk_dashboard_payload_is_frontend_ready():
    result = HelpDeskSimulationEngine().simulate(_scenario())
    payload = helpdesk_dashboard_payload(result)

    assert payload["schema_version"] == "1.0"
    assert payload["kind"] == "helpdesk_provisioning_simulation"
    assert "response" in payload
    assert "provisioning" in payload
    assert "workload" in payload
    assert "frontend" in payload
    assert payload["quality"]["sla_guaranteed"] is False
    assert "does not guarantee" in payload["disclaimer"]
