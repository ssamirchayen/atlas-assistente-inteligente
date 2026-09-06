from __future__ import annotations

import json
from typing import Any

from atlas.integrations.base import DriverKind, IntegrationResult
from atlas.integrations.business_lab.benchmark_runner import (
    PROVENANCE_LABEL,
    BusinessLabBenchmarkRunner,
    save_benchmark_report,
)
from atlas.integrations.business_lab.lab_runner import FORBIDDEN_SCENARIO_ACTIONS


class FakeBenchmarkConnector:
    def __init__(self, *, wrong_lead: bool = False) -> None:
        self.wrong_lead = wrong_lead
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, action: str, **kwargs: Any) -> IntegrationResult:
        self.calls.append((action, kwargs))

        if action in FORBIDDEN_SCENARIO_ACTIONS:
            return IntegrationResult(
                ok=False,
                action=action,
                driver=DriverKind.API,
                error="Ação proibida.",
            )

        if action == "get_lead":
            code = "SIM-99999" if self.wrong_lead else kwargs.get("code")
            return self._ok(
                action,
                {
                    "synthetic_code": code,
                    "name": "Lead Teste",
                    "course_name": "Radiologia",
                    "status": "novo",
                    "priority": "alta",
                },
            )

        return self._ok(action, {})

    def _ok(self, action: str, data: Any) -> IntegrationResult:
        return IntegrationResult(
            ok=True,
            action=action,
            driver=DriverKind.API,
            data=data,
        )


def test_benchmark_runner_measures_selected_scenarios() -> None:
    runner = BusinessLabBenchmarkRunner(FakeBenchmarkConnector())

    summary = runner.run(scenarios=("LAB-001", "LAB-010"), repetitions=2)

    assert summary.ok is True
    assert summary.total == 4
    assert summary.passed == 4
    assert summary.failed == 0
    assert summary.success_rate_percent == 100.0
    assert summary.average_elapsed_ms >= 0
    assert summary.provenance == PROVENANCE_LABEL


def test_benchmark_counts_failed_scenarios() -> None:
    runner = BusinessLabBenchmarkRunner(FakeBenchmarkConnector(wrong_lead=True))

    summary = runner.run(scenarios=("LAB-001",), repetitions=1)

    assert summary.ok is False
    assert summary.total == 1
    assert summary.passed == 0
    assert summary.failed == 1


def test_benchmark_rejects_invalid_arguments() -> None:
    runner = BusinessLabBenchmarkRunner(FakeBenchmarkConnector())

    try:
        runner.run(repetitions=0)
    except ValueError as error:
        assert "repetitions" in str(error)
    else:
        raise AssertionError("repetitions=0 deveria falhar")

    try:
        runner.run(scenarios=())
    except ValueError as error:
        assert "cenário" in str(error)
    else:
        raise AssertionError("scenarios vazio deveria falhar")


def test_save_benchmark_report_writes_json_and_csv(tmp_path) -> None:
    runner = BusinessLabBenchmarkRunner(FakeBenchmarkConnector())
    summary = runner.run(scenarios=("LAB-001",), repetitions=1)

    json_path, csv_path = save_benchmark_report(summary, output_dir=tmp_path)

    assert json_path.exists()
    assert csv_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["provenance"] == PROVENANCE_LABEL
    assert payload["total"] == 1
    assert "LAB-001" in csv_path.read_text(encoding="utf-8")
