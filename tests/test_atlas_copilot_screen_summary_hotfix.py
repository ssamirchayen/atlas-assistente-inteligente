from __future__ import annotations

from typing import Any

from atlas.copilot.business_lab import BusinessLabCopilotBridge
from atlas.integrations.base import DriverKind, IntegrationResult


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        self.calls.append((connector_name, action, kwargs))
        if action == "dashboard":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data={
                    "total_leads": 180,
                    "conversion_rate": 15.56,
                    "pending_followups": 50,
                    "overdue_followups": 42,
                },
            )
        if action == "list_leads":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data=[
                    {
                        "synthetic_code": "SIM-00001",
                        "status": "novo",
                        "priority": "alta",
                    },
                    {
                        "synthetic_code": "SIM-00002",
                        "status": "follow_up",
                        "priority": "media",
                    },
                ],
            )
        msg = f"Ação inesperada no teste: {action}"
        raise AssertionError(msg)


def test_summarize_screen_without_open_lead_does_not_fail() -> None:
    bridge = BusinessLabCopilotBridge(manager=FakeManager())

    response = bridge.handle(
        {
            "message": "Atlas, resuma essa tela",
            "context": {
                "page": "leads",
                "route": "/leads",
            },
        }
    )

    assert response.ok
    assert response.intent == "summarize_screen"
    assert "Resumo da tela Lista de leads" in response.answer
    assert response.data["screen_summary"]["high_priority"] == 1


def test_resume_dashboard_without_lead_falls_back_to_screen_summary() -> None:
    bridge = BusinessLabCopilotBridge(manager=FakeManager())

    response = bridge.handle(
        {
            "message": "Resumo do dashboard",
            "context": {
                "page": "index",
                "route": "/",
            },
        }
    )

    assert response.ok
    assert response.intent == "summarize_screen"
