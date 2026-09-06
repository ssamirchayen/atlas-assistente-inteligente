from __future__ import annotations

from typing import Any

from atlas.integrations.base import DriverKind, IntegrationResult
from atlas.integrations.business_lab.lab_runner import (
    FORBIDDEN_SCENARIO_ACTIONS,
    BusinessLabScenarioRunner,
)


class FakeBusinessLabConnector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, action: str, **kwargs: Any) -> IntegrationResult:
        self.calls.append((action, kwargs))

        if action in FORBIDDEN_SCENARIO_ACTIONS:
            return IntegrationResult(
                ok=False,
                action=action,
                error="Ação proibida ou não suportada.",
            )

        if action == "get_lead":
            return self._ok(
                action,
                {
                    "synthetic_code": kwargs.get("code"),
                    "name": "Lead Teste",
                    "course_name": "Radiologia",
                    "status": "novo",
                    "priority": "alta",
                },
            )

        if action == "list_courses":
            return self._ok(
                action,
                [
                    {"id": 1, "name": "Radiologia"},
                    {"id": 2, "name": "Administração"},
                ],
            )

        if action == "list_leads":
            return self._ok(
                action,
                [
                    {"synthetic_code": "SIM-00028"},
                    {"synthetic_code": "SIM-00144"},
                ],
                count=2,
            )

        if action == "list_interactions":
            return self._ok(
                action,
                [
                    {
                        "channel": "WhatsApp",
                        "direction": "entrada",
                        "outcome": "retorno_agendado",
                    }
                ],
                count=1,
            )

        if action == "create_interaction":
            return self._ok(action, {"id": 10, "lead": kwargs.get("code")})

        if action == "create_followup":
            return self._ok(
                action,
                {"id": 20, "lead": kwargs.get("code"), "status": "pendente"},
            )

        if action == "create_enrollment":
            return self._ok(
                action,
                {"enrollment_code": "MAT-00100", "synthetic_code": kwargs.get("code")},
            )

        if action == "update_enrollment":
            return self._ok(
                action,
                {
                    "enrollment_code": kwargs.get("code"),
                    "status": kwargs.get("status"),
                    "payment_status": kwargs.get("payment_status"),
                },
            )

        if action == "get_reports":
            return self._ok(action, {"indicators": {}, "filters": kwargs})

        return IntegrationResult(ok=False, action=action, error="Não mapeado.")

    def _ok(
        self,
        action: str,
        data: Any,
        *,
        count: int | None = None,
    ) -> IntegrationResult:
        metadata = {"api_meta": {"count": count}} if count is not None else {}
        return IntegrationResult(
            ok=True,
            action=action,
            driver=DriverKind.API,
            data=data,
            metadata=metadata,
        )


class DuplicateEnrollmentConnector(FakeBusinessLabConnector):
    def execute(self, action: str, **kwargs: Any) -> IntegrationResult:
        if action == "create_enrollment":
            return IntegrationResult(
                ok=False,
                action=action,
                driver=DriverKind.API,
                error="Este lead já possui matrícula.",
            )
        return super().execute(action, **kwargs)


def test_runner_executes_all_labs_without_forbidden_answer_actions() -> None:
    connector = FakeBusinessLabConnector()
    runner = BusinessLabScenarioRunner(connector)

    summary = runner.run_all()

    assert summary.ok is True
    assert summary.total == 10
    assert summary.passed == 10

    regular_actions = [
        action
        for action, _kwargs in connector.calls
        if action not in FORBIDDEN_SCENARIO_ACTIONS
    ]
    assert "get_lead" in regular_actions
    assert "get_reports" in regular_actions
    assert "scenario_answer" not in regular_actions


def test_lab002_finds_radiologia_before_filtering_leads() -> None:
    connector = FakeBusinessLabConnector()
    runner = BusinessLabScenarioRunner(connector)

    record = runner.run("LAB-002")

    assert record.ok is True
    assert record.data["course_id"] == 1
    assert record.data["count"] == 2
    assert connector.calls[-1] == (
        "list_leads",
        {"course_id": 1, "priority": "alta", "limit": 200},
    )


def test_lab006_accepts_existing_enrollment_as_final_state() -> None:
    connector = DuplicateEnrollmentConnector()
    runner = BusinessLabScenarioRunner(connector)

    record = runner.run("LAB-006")

    assert record.ok is True
    assert record.data["already_exists"] is True


def test_unknown_lab_id_returns_failure() -> None:
    runner = BusinessLabScenarioRunner(FakeBusinessLabConnector())

    record = runner.run("LAB-999")

    assert record.ok is False
    assert record.action == "unknown"


def test_lab010_blocks_official_scenario_access() -> None:
    runner = BusinessLabScenarioRunner(FakeBusinessLabConnector())

    record = runner.run("LAB-010")

    assert record.ok is True
    forbidden = record.data["forbidden_actions"]
    assert len(forbidden) == len(FORBIDDEN_SCENARIO_ACTIONS)
    assert all(item["blocked"] for item in forbidden)
