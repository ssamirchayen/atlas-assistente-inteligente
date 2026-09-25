from __future__ import annotations

import json
import threading
from typing import Any
from urllib.request import Request, urlopen

from atlas.copilot.business_lab import BusinessLabCopilotBridge
from atlas.copilot.local_api import create_copilot_server
from atlas.copilot.models import CopilotResponse
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
        if action == "get_lead":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data={
                    "synthetic_code": kwargs["code"],
                    "name": "Larissa Silva",
                    "course_name": "Enfermagem",
                    "status": "follow_up",
                    "priority": "alta",
                    "source": "Site",
                },
            )
        if action in {"list_interactions", "list_followups"}:
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data=[],
            )
        if action == "create_interaction":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data={"id": 99, "lead": kwargs["code"]},
            )
        if action == "list_courses":
            return IntegrationResult(
                ok=True,
                action=action,
                driver=DriverKind.API,
                data=[{"id": 1, "name": "Radiologia"}],
            )
        return IntegrationResult(
            ok=True,
            action=action,
            driver=DriverKind.API,
            data={},
        )


def test_bridge_summarizes_open_lead() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": "Resuma esse lead",
            "context": {
                "page": "lead_detail",
                "lead_code": "SIM-00001",
            },
        }
    )

    assert response.ok is True
    assert response.intent == "summarize_lead"
    assert "Larissa Silva" in response.answer
    assert manager.calls[0][1] == "get_lead"


def test_bridge_requires_lead_for_lead_actions() -> None:
    bridge = BusinessLabCopilotBridge(manager=FakeManager())

    response = bridge.handle(
        {
            "message": "Resuma esse lead",
            "context": {"page": "dashboard"},
        }
    )

    assert response.ok is False
    assert response.intent == "summarize_lead"
    assert "Nenhum lead aberto" in response.answer


def test_bridge_can_dry_run_interaction() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": "Registre atendimento dizendo que pediu retorno amanhã",
            "dry_run": True,
            "context": {
                "page": "lead_detail",
                "lead_code": "SIM-00005",
            },
        }
    )

    assert response.ok is True
    assert response.intent == "create_interaction"
    assert manager.calls == []
    assert "Modo simulação" in response.answer


def test_bridge_creates_interaction_through_integration_manager() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": "Registre atendimento dizendo que aluno pediu boleto",
            "context": {
                "page": "lead_detail",
                "lead_code": "SIM-00005",
            },
        }
    )

    assert response.ok is True
    assert response.intent == "create_interaction"
    assert manager.calls[0][1] == "create_interaction"
    assert manager.calls[0][2]["code"] == "SIM-00005"


def test_local_api_health_and_message_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_COPILOT_TOKEN", "different-environment-test-token")
    def handler(payload: dict[str, Any]) -> CopilotResponse:
        assert payload["message"] == "teste"
        return CopilotResponse(ok=True, answer="ok", intent="test")

    server = create_copilot_server(
        host="127.0.0.1",
        port=0,
        copilot_handler=handler,
        api_token="copilot-test-token-local-only",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urlopen(f"{base_url}/health", timeout=2) as response:
            health = json.loads(response.read().decode("utf-8"))
        assert health["ok"] is True

        body = json.dumps({"message": "teste"}).encode("utf-8")
        request = Request(
            f"{base_url}/api/copilot/message",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Atlas-Copilot-Token": "copilot-test-token-local-only",
            },
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        assert decoded["ok"] is True
        assert decoded["data"]["answer"] == "ok"
    finally:
        server.shutdown()
        server.server_close()
