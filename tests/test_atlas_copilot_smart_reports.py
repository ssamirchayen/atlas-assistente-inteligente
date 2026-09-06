from __future__ import annotations

from typing import Any

from atlas.copilot.business_lab import BusinessLabCopilotBridge
from atlas.copilot.smart_reports import looks_like_smart_report_command
from atlas.integrations.base import DriverKind, IntegrationResult
from atlas.integrations.business_lab.api_driver import BusinessLabApiDriver


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
        if action == "list_courses":
            return _ok(action, [{"id": 7, "name": "Radiologia"}])
        if action == "get_reports":
            return _ok(action, _sample_report())
        if action == "list_leads":
            return _ok(action, _sample_leads())
        if action == "list_enrollments":
            return _ok(action, _sample_enrollments())
        if action == "list_all_followups":
            return _ok(action, _sample_followups())
        if action == "list_recent_interactions":
            return _ok(action, _sample_interactions())
        if action == "dashboard":
            return _ok(action, {"schema_version": 7})
        msg = f"Ação inesperada no teste: {action}"
        raise AssertionError(msg)


def test_detects_smart_report_commands() -> None:
    assert looks_like_smart_report_command(
        "Atlas, gere relatório completo dos leads de Radiologia."
    )
    assert looks_like_smart_report_command(
        "Analise atendimentos e diga onde perdemos conversão."
    )
    assert not looks_like_smart_report_command("Resuma esse lead")


def test_bridge_generates_smart_report_with_exports() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": (
                "Atlas, gere um relatório completo dos leads, matrículas, "
                "atendimentos e retornos de Radiologia desta semana."
            ),
            "context": {"page": "reports", "route": "/relatorios"},
        }
    )

    assert response.ok
    assert response.intent == "smart_reports"
    assert "Relatório inteligente" in response.answer
    assert response.data["report"]["filters"]["course_name"] == "Radiologia"
    assert response.data["report"]["filters"]["period_label"] == "esta semana"
    assert "markdown" in response.data["exports"]
    assert "csv" in response.data["exports"]
    assert "html" in response.data["exports"]


def test_smart_report_uses_filters_and_global_actions() -> None:
    manager = FakeManager()
    bridge = BusinessLabCopilotBridge(manager=manager)

    response = bridge.handle(
        {
            "message": (
                "Atlas, liste retornos atrasados de Radiologia prioridade alta."
            ),
            "context": {"page": "reports"},
        }
    )

    assert response.ok
    calls = {call[1]: call[2] for call in manager.calls}
    assert calls["get_reports"]["course_id"] == 7
    assert calls["list_leads"]["course_id"] == 7
    assert calls["list_leads"]["priority"] == "alta"
    assert calls["list_all_followups"]["due_filter"] == "atrasado"
    assert calls["list_all_followups"]["priority"] == "alta"
    assert calls["list_recent_interactions"]["limit"] == 50


def test_smart_report_builds_insights_alerts_and_next_steps() -> None:
    response = BusinessLabCopilotBridge(manager=FakeManager()).handle(
        {
            "message": "Atlas, analise atendimentos e conversão da operação.",
            "context": {"page": "reports"},
        }
    )

    report = response.data["report"]
    assert report["metrics"]["total_leads_reportado"] == 180
    assert report["metrics"]["retornos_atrasados_na_amostra"] == 1
    assert report["insights"]
    assert report["alerts"]
    assert report["next_steps"]


def test_api_driver_supports_smart_report_global_actions() -> None:
    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055",
        email="consultor@nexyra.lab",
        password="Consultor123!",
    )

    assert driver.supports("list_recent_interactions")
    assert driver.supports("list_all_followups")
    assert driver.supports("get_reports")


def _ok(action: str, data: Any) -> IntegrationResult:
    return IntegrationResult(
        ok=True,
        action=action,
        driver=DriverKind.API,
        data=data,
    )


def _sample_report() -> dict[str, Any]:
    return {
        "total_leads": 180,
        "converted_leads": 20,
        "conversion_rate": 11.11,
        "total_interactions": 320,
        "pending_followups": 26,
        "overdue_followups": 4,
        "total_enrollments": 20,
        "active_enrollments": 18,
        "confirmed_payments": 14,
        "monthly_projection": 6900.0,
        "funnel": [
            {"status": "novo", "total": 50, "percentage": 27.78},
            {"status": "convertido", "total": 20, "percentage": 11.11},
        ],
        "sources": [
            {
                "source": "WhatsApp",
                "total": 80,
                "converted": 6,
                "conversion_rate": 7.5,
            }
        ],
        "courses": [
            {
                "id": 7,
                "name": "Radiologia",
                "leads": 40,
                "converted": 4,
                "enrollments": 4,
                "active_enrollments": 3,
                "conversion_rate": 10.0,
            }
        ],
    }


def _sample_leads() -> list[dict[str, Any]]:
    return [
        {
            "synthetic_code": "SIM-00001",
            "name": "Larissa Silva",
            "course_name": "Radiologia",
            "status": "novo",
            "priority": "alta",
            "source": "WhatsApp",
        },
        {
            "synthetic_code": "SIM-00002",
            "name": "Felipe Martins",
            "course_name": "Radiologia",
            "status": "follow_up",
            "priority": "alta",
            "source": "Instagram",
        },
    ]


def _sample_enrollments() -> list[dict[str, Any]]:
    return [
        {
            "enrollment_code": "MAT-00001",
            "student_name": "Larissa Silva",
            "course_name": "Radiologia",
            "status": "ativa",
            "payment_status": "confirmado",
        }
    ]


def _sample_followups() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "synthetic_code": "SIM-00001",
            "lead_name": "Larissa Silva",
            "course_name": "Radiologia",
            "status": "pendente",
            "priority": "alta",
            "is_overdue": 1,
        }
    ]


def _sample_interactions() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "synthetic_code": "SIM-00001",
            "lead_name": "Larissa Silva",
            "channel": "WhatsApp",
            "kind": "mensagem",
            "outcome": "interessado",
        }
    ]
