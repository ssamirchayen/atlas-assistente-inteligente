from __future__ import annotations

from typing import Any

from atlas.copilot.batch_messages import looks_like_batch_message_command
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
        if action == "create_interaction":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data={"id": len(self.calls), **kwargs},
            )
        if action == "create_followup":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data={"id": len(self.calls), **kwargs},
            )
        if action == "update_lead_status":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data={"id": len(self.calls), **kwargs},
            )
        msg = f"Ação inesperada no teste: {action}"
        raise AssertionError(msg)


class FailingManager(FakeManager):
    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        if action == "create_interaction":
            self.calls.append((connector_name, action, kwargs))
            return IntegrationResult(
                ok=False,
                action=action,
                driver=DriverKind.API,
                error="falha simulada",
            )
        return super().execute(connector_name, action, **kwargs)


def test_detects_batch_message_commands() -> None:
    assert looks_like_batch_message_command(
        "Atlas, prepare mensagens para 10 leads de Radiologia."
    )
    assert looks_like_batch_message_command(
        "Registre atendimentos em lote para os leads em follow-up."
    )
    assert not looks_like_batch_message_command("Resuma esse lead")


def test_batch_messages_returns_preview_without_execution() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": (
                "Atlas, prepare mensagens para 10 leads novos de Radiologia "
                "e crie retornos para amanhã às 15h."
            ),
            "context": {"page": "leads_list", "route": "/leads"},
        }
    )

    assert response.ok
    assert response.intent == "batch_messages"
    assert response.requires_human_review
    assert "Prévia" in response.answer
    assert response.data["confirmation_required"] is True
    assert response.data["external_delivery"] == "disabled"
    assert response.data["execution_plan"]["mode"] == "preview_only"
    assert response.data["execution_plan"]["executed_actions"] == []
    assert response.data["status_update_plan"]["enabled"] is True
    assert response.data["status_update_plan"]["target_status"] == "follow_up"

    executed = [
        call
        for call in manager.calls
        if call[1] in {"create_interaction", "create_followup", "update_lead_status"}
    ]
    assert executed == []


def test_batch_messages_uses_filters_and_generates_personalized_messages() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": (
                "Atlas, envie mensagem para 5 leads de Radiologia "
                "prioridade alta."
            ),
            "context": {"page": "leads_list"},
        }
    )

    assert response.ok
    assert response.data["filters"]["course_id"] == 7
    assert response.data["filters"]["priority"] == "alta"
    assert response.data["selected_count"] == 3
    first_message = response.data["messages"][0]["message"]
    assert "Radiologia" in first_message
    assert "Olá" in first_message

    list_leads_call = [call for call in manager.calls if call[1] == "list_leads"][0]
    assert list_leads_call[2]["course_id"] == 7
    assert list_leads_call[2]["priority"] == "alta"


def test_batch_messages_confirmed_registers_interactions_and_followups() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": (
                "Atlas, registre atendimentos em lote para 2 leads de Radiologia "
                "e crie retornos amanhã às 15h."
            ),
            "context": {"page": "leads_list"},
            "confirmed": True,
        }
    )

    assert response.ok
    assert response.intent == "batch_messages"
    assert response.data["mode"] == "confirmed_business_lab_records"
    assert response.data["execution"]["interaction_success"] == 2
    assert response.data["execution"]["followup_success"] == 2
    assert response.data["execution"]["status_success"] == 1
    assert response.data["execution"]["status_skipped"] == 1
    assert response.data["execution"]["target_status"] == "follow_up"

    interactions = [call for call in manager.calls if call[1] == "create_interaction"]
    followups = [call for call in manager.calls if call[1] == "create_followup"]
    status_updates = [call for call in manager.calls if call[1] == "update_lead_status"]
    assert len(interactions) == 2
    assert len(followups) == 2
    assert len(status_updates) == 1
    assert status_updates[0][2]["status"] == "follow_up"
    assert interactions[0][2]["kind"] == "mensagem"
    assert "WhatsApp" in {call[2]["channel"] for call in interactions}


def test_batch_messages_allows_explicit_status_update() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": (
                "Atlas, registre atendimentos para 2 leads de Radiologia "
                "e atualize status para em atendimento."
            ),
            "context": {"page": "leads_list"},
            "confirmed": True,
        }
    )

    assert response.ok
    assert response.data["execution"]["target_status"] == "em_atendimento"

    status_updates = [call for call in manager.calls if call[1] == "update_lead_status"]
    assert len(status_updates) == 2
    assert {call[2]["status"] for call in status_updates} == {"em_atendimento"}


def test_batch_messages_blocks_confirmed_execution_above_safe_limit() -> None:
    manager = FakeManager(leads=_many_leads(30))
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": "Atlas, registre mensagens para 30 leads de Radiologia.",
            "context": {"page": "leads_list"},
            "confirmed": True,
        }
    )

    assert not response.ok
    assert "Bloqueei" in response.answer
    assert response.data["mode"] == "blocked_by_safety_limit"
    assert response.data["limit"] == 25

    interactions = [call for call in manager.calls if call[1] == "create_interaction"]
    assert interactions == []


def test_batch_messages_reports_execution_failures() -> None:
    bridge = BusinessLabCopilotBridge(manager=FailingManager())

    response = bridge.handle(
        {
            "message": "Atlas, registre atendimento em lote para 2 leads.",
            "context": {"page": "leads_list"},
            "confirmed": True,
        }
    )

    assert not response.ok
    assert response.data["execution"]["interaction_failed"] == 2
    assert "Alguns itens falharam" in response.answer


def _sample_leads() -> list[dict[str, Any]]:
    return [
        {
            "synthetic_code": "SIM-00001",
            "name": "Larissa Silva",
            "course_name": "Radiologia",
            "status": "novo",
            "priority": "alta",
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
            "course_name": "Radiologia",
            "status": "em_atendimento",
            "priority": "media",
            "source": "Instagram",
        },
    ]


def _many_leads(total: int) -> list[dict[str, Any]]:
    return [
        {
            "synthetic_code": f"SIM-{index:05d}",
            "name": f"Lead {index}",
            "course_name": "Radiologia",
            "status": "novo",
            "priority": "alta",
            "source": "WhatsApp",
        }
        for index in range(1, total + 1)
    ]
