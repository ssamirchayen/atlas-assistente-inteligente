from __future__ import annotations

from typing import Any

from atlas.copilot.batch_leads import looks_like_batch_lead_triage
from atlas.copilot.business_lab import BusinessLabCopilotBridge
from atlas.integrations.base import DriverKind, IntegrationResult


class FakeManager:
    def __init__(self, leads: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.leads = leads if leads is not None else _sample_leads()

    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        self.calls.append((connector_name, action, kwargs))
        if action == "list_courses":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data=[
                    {"id": 7, "name": "Radiologia"},
                    {"id": 8, "name": "Administração"},
                ],
            )
        if action == "list_leads":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data=self.leads,
            )
        msg = f"Ação inesperada no teste: {action}"
        raise AssertionError(msg)


def test_detects_batch_lead_triage_commands() -> None:
    assert looks_like_batch_lead_triage(
        "Atlas, analise os 10 leads novos de Radiologia."
    )
    assert looks_like_batch_lead_triage(
        "Faça uma triagem em lote dos leads pendentes."
    )
    assert not looks_like_batch_lead_triage("Resuma esse lead")


def test_batch_triage_uses_filters_and_returns_safe_preview() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": (
                "Atlas, analise os 10 leads novos de Radiologia "
                "com prioridade alta."
            ),
            "context": {"page": "leads_list", "route": "/leads"},
        }
    )

    assert response.ok
    assert response.intent == "batch_lead_triage"
    assert response.requires_human_review
    assert "Triagem em lote pronta" in response.answer
    assert response.data["filters"]["course_id"] == 7
    assert response.data["filters"]["status"] == "novo"
    assert response.data["filters"]["priority"] == "alta"
    assert response.data["execution_plan"]["mode"] == "preview_only"
    assert response.data["execution_plan"]["executed_actions"] == []

    list_leads_call = [call for call in manager.calls if call[1] == "list_leads"][0]
    assert list_leads_call[2]["course_id"] == 7
    assert list_leads_call[2]["status"] == "novo"
    assert list_leads_call[2]["priority"] == "alta"


def test_batch_triage_prioritizes_high_value_leads() -> None:
    bridge = BusinessLabCopilotBridge(manager=FakeManager())

    response = bridge.handle(
        {
            "message": "Atlas, faça triagem em lote dos leads pendentes.",
            "context": {"page": "leads_list"},
        }
    )

    selected = response.data["selected"]
    assert selected[0]["code"] == "SIM-00002"
    assert selected[0]["priority"] == "alta"
    assert "retomar conversa" in selected[0]["recommended_action"]


def test_batch_triage_handles_empty_result() -> None:
    bridge = BusinessLabCopilotBridge(manager=FakeManager(leads=[]))

    response = bridge.handle(
        {
            "message": "Atlas, analise vários leads de Radiologia.",
            "context": {"page": "leads_list"},
        }
    )

    assert response.ok
    assert response.data["total_candidates"] == 0
    assert response.data["selected"] == []
    assert "Não encontrei leads" in response.answer


def _sample_leads() -> list[dict[str, Any]]:
    return [
        {
            "synthetic_code": "SIM-00001",
            "name": "Larissa Silva",
            "course_name": "Radiologia",
            "status": "novo",
            "priority": "media",
            "source": "Site",
        },
        {
            "synthetic_code": "SIM-00002",
            "name": "Felipe Martins",
            "course_name": "Radiologia",
            "status": "follow_up",
            "priority": "alta",
            "source": "WhatsApp",
        },
        {
            "synthetic_code": "SIM-00003",
            "name": "Gabriela Souza",
            "course_name": "Administração",
            "status": "perdido",
            "priority": "baixa",
            "source": "Instagram",
        },
    ]
