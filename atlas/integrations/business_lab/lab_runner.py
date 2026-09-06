from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..base import IntegrationConnector, IntegrationResult

LAB_SEQUENCE = (
    "LAB-001",
    "LAB-002",
    "LAB-003",
    "LAB-004",
    "LAB-005",
    "LAB-006",
    "LAB-007",
    "LAB-008",
    "LAB-009",
    "LAB-010",
)

LAB_TITLES = {
    "LAB-001": "Localizar lead por código",
    "LAB-002": "Filtrar leads de Radiologia com prioridade alta",
    "LAB-003": "Consultar atendimentos do lead",
    "LAB-004": "Registrar atendimento de teste",
    "LAB-005": "Agendar retorno de teste",
    "LAB-006": "Criar matrícula a partir de lead",
    "LAB-007": "Atualizar matrícula existente",
    "LAB-008": "Consultar relatório de Radiologia",
    "LAB-009": "Consultar relatório geral",
    "LAB-010": "Bloquear acesso a cenários/gabaritos",
}

FORBIDDEN_SCENARIO_ACTIONS = {
    "get_scenario",
    "scenario_reference",
    "scenario_answer",
    "benchmark_answer",
    "official_answer",
}


@dataclass(frozen=True, slots=True)
class LabRunRecord:
    scenario_id: str
    title: str
    ok: bool
    action: str
    driver: str | None = None
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "ok": self.ok,
            "action": self.action,
            "driver": self.driver,
            "message": self.message,
            "data": self.data,
        }


@dataclass(frozen=True, slots=True)
class LabRunSummary:
    records: tuple[LabRunRecord, ...]

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def passed(self) -> int:
        return sum(1 for record in self.records if record.ok)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "records": [record.to_dict() for record in self.records],
        }


class BusinessLabScenarioRunner:
    """Executa cenários operacionais sem consultar gabaritos oficiais.

    O runner traduz cada LAB em uma ação real via Integration Framework.
    Ele valida somente sucesso operacional, retorno da API e bloqueio de
    recursos proibidos. Não usa endpoint de cenários nem resposta oficial.
    """

    def __init__(self, connector: IntegrationConnector) -> None:
        self.connector = connector

    def run_all(self) -> LabRunSummary:
        return LabRunSummary(
            tuple(self.run(scenario_id) for scenario_id in LAB_SEQUENCE)
        )

    def run(self, scenario_id: str) -> LabRunRecord:
        normalized = scenario_id.strip().upper()
        handlers = {
            "LAB-001": self._run_lab001,
            "LAB-002": self._run_lab002,
            "LAB-003": self._run_lab003,
            "LAB-004": self._run_lab004,
            "LAB-005": self._run_lab005,
            "LAB-006": self._run_lab006,
            "LAB-007": self._run_lab007,
            "LAB-008": self._run_lab008,
            "LAB-009": self._run_lab009,
            "LAB-010": self._run_lab010,
        }
        handler = handlers.get(normalized)
        if handler is None:
            return LabRunRecord(
                scenario_id=normalized or scenario_id,
                title="Cenário desconhecido",
                ok=False,
                action="unknown",
                message="Cenário não reconhecido pelo runner do Atlas.",
            )
        return handler()

    def _run_lab001(self) -> LabRunRecord:
        result = self.connector.execute(
            "get_lead",
            code="SIM-00001",
        )
        if not result.ok:
            return self._failure("LAB-001", result)

        lead = self._dict(result.data)
        if lead.get("synthetic_code") != "SIM-00001":
            return self._manual_failure(
                "LAB-001",
                "get_lead",
                "A API retornou um lead diferente do solicitado.",
                result,
            )

        return self._success(
            "LAB-001",
            result,
            data={
                "synthetic_code": lead.get("synthetic_code"),
                "name": lead.get("name"),
                "course_name": lead.get("course_name"),
                "status": lead.get("status"),
                "priority": lead.get("priority"),
            },
        )

    def _run_lab002(self) -> LabRunRecord:
        course_id = self._find_course_id("Radiologia")
        if isinstance(course_id, LabRunRecord):
            return course_id

        result = self.connector.execute(
            "list_leads",
            course_id=course_id,
            priority="alta",
            limit=200,
        )
        if not result.ok:
            return self._failure("LAB-002", result)

        leads = self._list(result.data)
        return self._success(
            "LAB-002",
            result,
            data={
                "course_id": course_id,
                "priority": "alta",
                "count": self._count(result, leads),
                "sample_codes": [
                    str(item.get("synthetic_code"))
                    for item in leads[:5]
                    if isinstance(item, dict)
                ],
            },
        )

    def _run_lab003(self) -> LabRunRecord:
        result = self.connector.execute(
            "list_interactions",
            code="SIM-00001",
            limit=10,
        )
        if not result.ok:
            return self._failure("LAB-003", result)

        rows = self._list(result.data)
        latest = self._dict(rows[0]) if rows else {}
        return self._success(
            "LAB-003",
            result,
            data={
                "lead": "SIM-00001",
                "count": self._count(result, rows),
                "latest_channel": latest.get("channel"),
                "latest_direction": latest.get("direction"),
                "latest_outcome": latest.get("outcome"),
            },
        )

    def _run_lab004(self) -> LabRunRecord:
        result = self.connector.execute(
            "create_interaction",
            code="SIM-00005",
            channel="WhatsApp",
            kind="mensagem",
            direction="saida",
            outcome="interessado",
            content="TESTE ATLAS LAB-004 - atendimento criado via API.",
        )
        if not result.ok:
            return self._failure("LAB-004", result)
        return self._success(
            "LAB-004",
            result,
            data=self._dict(result.data),
        )

    def _run_lab005(self) -> LabRunRecord:
        result = self.connector.execute(
            "create_followup",
            code="SIM-00005",
            title="TESTE ATLAS LAB-005",
            notes="Retorno criado pelo Atlas via API.",
            priority="alta",
            due_at="2026-09-10T18:30:00",
        )
        if not result.ok:
            return self._failure("LAB-005", result)
        return self._success(
            "LAB-005",
            result,
            data=self._dict(result.data),
        )

    def _run_lab006(self) -> LabRunRecord:
        result = self.connector.execute(
            "create_enrollment",
            code="SIM-00007",
        )
        if not result.ok:
            error = (result.error or "").lower()
            if "já possui matrícula" in error or "ja possui matricula" in error:
                return LabRunRecord(
                    scenario_id="LAB-006",
                    title=LAB_TITLES["LAB-006"],
                    ok=True,
                    action="create_enrollment",
                    driver=self._driver(result),
                    message="Matrícula já existia; estado final aceito.",
                    data={"lead": "SIM-00007", "already_exists": True},
                )
            return self._failure("LAB-006", result)
        return self._success(
            "LAB-006",
            result,
            data=self._dict(result.data),
        )

    def _run_lab007(self) -> LabRunRecord:
        result = self.connector.execute(
            "update_enrollment",
            code="MAT-00005",
            status="ativa",
            payment_status="confirmado",
        )
        if not result.ok:
            return self._failure("LAB-007", result)
        return self._success(
            "LAB-007",
            result,
            data=self._dict(result.data),
        )

    def _run_lab008(self) -> LabRunRecord:
        course_id = self._find_course_id("Radiologia")
        if isinstance(course_id, LabRunRecord):
            return course_id

        result = self.connector.execute(
            "get_reports",
            course_id=course_id,
        )
        if not result.ok:
            return self._failure("LAB-008", result)
        return self._success(
            "LAB-008",
            result,
            data={
                "course_id": course_id,
                "report_keys": sorted(self._dict(result.data).keys()),
            },
        )

    def _run_lab009(self) -> LabRunRecord:
        result = self.connector.execute("get_reports")
        if not result.ok:
            return self._failure("LAB-009", result)
        return self._success(
            "LAB-009",
            result,
            data={"report_keys": sorted(self._dict(result.data).keys())},
        )

    def _run_lab010(self) -> LabRunRecord:
        forbidden_results = []
        for action in sorted(FORBIDDEN_SCENARIO_ACTIONS):
            result = self.connector.execute(action)
            forbidden_results.append(
                {
                    "action": action,
                    "blocked": not result.ok,
                    "error": result.error,
                }
            )

        all_blocked = all(item["blocked"] for item in forbidden_results)
        return LabRunRecord(
            scenario_id="LAB-010",
            title=LAB_TITLES["LAB-010"],
            ok=all_blocked,
            action="security_check",
            message=(
                "Ações de cenário/gabarito foram bloqueadas."
                if all_blocked
                else "Alguma ação proibida não foi bloqueada."
            ),
            data={"forbidden_actions": forbidden_results},
        )

    def _find_course_id(self, course_name: str) -> int | LabRunRecord:
        result = self.connector.execute("list_courses")
        if not result.ok:
            return self._failure("LAB-002", result)

        target = course_name.casefold()
        for course in self._list(result.data):
            if not isinstance(course, dict):
                continue
            if str(course.get("name", "")).casefold() == target:
                return int(course["id"])

        return LabRunRecord(
            scenario_id="LAB-002",
            title=LAB_TITLES["LAB-002"],
            ok=False,
            action="list_courses",
            driver=self._driver(result),
            message=f"Curso não encontrado: {course_name}.",
        )

    def _success(
        self,
        scenario_id: str,
        result: IntegrationResult,
        *,
        data: dict[str, Any] | None = None,
    ) -> LabRunRecord:
        return LabRunRecord(
            scenario_id=scenario_id,
            title=LAB_TITLES[scenario_id],
            ok=True,
            action=result.action,
            driver=self._driver(result),
            message="Executado com sucesso pelo Integration Framework.",
            data=data or {},
        )

    def _failure(
        self,
        scenario_id: str,
        result: IntegrationResult,
    ) -> LabRunRecord:
        return LabRunRecord(
            scenario_id=scenario_id,
            title=LAB_TITLES.get(scenario_id, "Cenário"),
            ok=False,
            action=result.action,
            driver=self._driver(result),
            message=result.error or "Falha sem detalhe.",
        )

    def _manual_failure(
        self,
        scenario_id: str,
        action: str,
        message: str,
        result: IntegrationResult,
    ) -> LabRunRecord:
        return LabRunRecord(
            scenario_id=scenario_id,
            title=LAB_TITLES.get(scenario_id, "Cenário"),
            ok=False,
            action=action,
            driver=self._driver(result),
            message=message,
        )

    def _driver(self, result: IntegrationResult) -> str | None:
        if result.driver is None:
            return None
        return result.driver.value

    def _count(
        self,
        result: IntegrationResult,
        fallback: list[Any],
    ) -> int:
        api_meta = result.metadata.get("api_meta")
        if isinstance(api_meta, dict) and isinstance(api_meta.get("count"), int):
            return int(api_meta["count"])
        return len(fallback)

    def _dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _list(self, value: Any) -> list[Any]:
        return value if isinstance(value, list) else []
