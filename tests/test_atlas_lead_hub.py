from __future__ import annotations

from atlas.lead_hub.command_parser import parse_lead_hub_command
from atlas.lead_hub.models import LeadRecord
from atlas.lead_hub.service import LeadHubService


class FakeClient:
    def pull(self, request):
        return {
            "ok": True,
            "processed_count": len(request.leads),
            "contact_ready_count": len(request.leads),
            "source": request.source,
        }


def test_parse_detects_lead_capture_command():
    command = parse_lead_hub_command("Atlas, puxe os leads da internet e organize no sistema")
    assert command.is_lead_hub_command is True
    assert command.source == "internet"
    assert command.auto_triage is True


def test_parse_detects_sunchat_source_and_contact_preparation():
    command = parse_lead_hub_command("Atlas, capture os leads do SunChat e prepare contato")
    assert command.is_lead_hub_command is True
    assert command.source == "sunchat"
    assert command.channel == "sunchat"
    assert command.prepare_contact is True


def test_parse_requires_lead_and_action_terms():
    command = parse_lead_hub_command("Atlas, abra o dashboard")
    assert command.is_lead_hub_command is False


def test_lead_identity_prefers_phone():
    lead = LeadRecord(name="Maria", phone="(92) 98800-1100", email="x@y.com")
    assert lead.identity_key() == "phone:92988001100"


def test_service_runs_demo_leads():
    result = LeadHubService(client=FakeClient()).run_from_command(
        "Atlas, puxe os leads da internet e prepare contato",
        demo=True,
    )
    assert result.ok is True
    assert "Leads captados" in result.message
    assert result.payload["processed_count"] > 0
