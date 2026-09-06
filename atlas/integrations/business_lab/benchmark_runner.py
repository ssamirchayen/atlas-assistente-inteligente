from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from ..base import IntegrationConnector
from .lab_runner import LAB_SEQUENCE, BusinessLabScenarioRunner

PROVENANCE_LABEL = "MEASURED_IN_LOCAL_BUSINESS_LAB"
DEFAULT_OUTPUT_DIR = Path("data") / "business_lab_benchmark"


@dataclass(frozen=True, slots=True)
class BusinessLabBenchmarkSample:
    scenario_id: str
    repetition: int
    ok: bool
    elapsed_ms: float
    action: str
    driver: str | None
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "repetition": self.repetition,
            "ok": self.ok,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "action": self.action,
            "driver": self.driver,
            "message": self.message,
            "data": self.data,
        }


@dataclass(frozen=True, slots=True)
class BusinessLabBenchmarkSummary:
    started_at: str
    finished_at: str
    provenance: str
    repetitions: int
    samples: tuple[BusinessLabBenchmarkSample, ...]

    @property
    def total(self) -> int:
        return len(self.samples)

    @property
    def passed(self) -> int:
        return sum(1 for sample in self.samples if sample.ok)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0

    @property
    def success_rate_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.passed / self.total) * 100, 2)

    @property
    def total_elapsed_ms(self) -> float:
        return round(sum(sample.elapsed_ms for sample in self.samples), 3)

    @property
    def average_elapsed_ms(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.total_elapsed_ms / self.total, 3)

    @property
    def median_elapsed_ms(self) -> float:
        if self.total == 0:
            return 0.0
        return round(statistics.median(sample.elapsed_ms for sample in self.samples), 3)

    @property
    def slowest_sample(self) -> BusinessLabBenchmarkSample | None:
        if not self.samples:
            return None
        return max(self.samples, key=lambda sample: sample.elapsed_ms)

    @property
    def fastest_sample(self) -> BusinessLabBenchmarkSample | None:
        if not self.samples:
            return None
        return min(self.samples, key=lambda sample: sample.elapsed_ms)

    def to_dict(self) -> dict[str, Any]:
        fastest = self.fastest_sample
        slowest = self.slowest_sample
        return {
            "ok": self.ok,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "provenance": self.provenance,
            "repetitions": self.repetitions,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "success_rate_percent": self.success_rate_percent,
            "total_elapsed_ms": self.total_elapsed_ms,
            "average_elapsed_ms": self.average_elapsed_ms,
            "median_elapsed_ms": self.median_elapsed_ms,
            "fastest": fastest.to_dict() if fastest else None,
            "slowest": slowest.to_dict() if slowest else None,
            "samples": [sample.to_dict() for sample in self.samples],
        }


class BusinessLabBenchmarkRunner:
    """Mede a execução real dos LABs pelo Integration Framework.

    Este runner não usa gabaritos oficiais e não consulta /api/v1/cenarios.
    Ele mede tempo, sucesso, driver usado e resultado operacional para relatórios
    técnicos do Atlas contra um sistema externo controlado.
    """

    def __init__(self, connector: IntegrationConnector) -> None:
        self.connector = connector

    def run(
        self,
        *,
        scenarios: tuple[str, ...] = LAB_SEQUENCE,
        repetitions: int = 1,
    ) -> BusinessLabBenchmarkSummary:
        if repetitions < 1:
            raise ValueError("repetitions precisa ser maior ou igual a 1.")
        if not scenarios:
            raise ValueError("Informe pelo menos um cenário para medir.")

        started = _utc_now()
        lab_runner = BusinessLabScenarioRunner(self.connector)
        samples: list[BusinessLabBenchmarkSample] = []

        for repetition in range(1, repetitions + 1):
            for scenario_id in scenarios:
                normalized = scenario_id.strip().upper()
                start = perf_counter()
                record = lab_runner.run(normalized)
                elapsed_ms = (perf_counter() - start) * 1000
                samples.append(
                    BusinessLabBenchmarkSample(
                        scenario_id=record.scenario_id,
                        repetition=repetition,
                        ok=record.ok,
                        elapsed_ms=elapsed_ms,
                        action=record.action,
                        driver=record.driver,
                        message=record.message,
                        data=record.data,
                    )
                )

        return BusinessLabBenchmarkSummary(
            started_at=started,
            finished_at=_utc_now(),
            provenance=PROVENANCE_LABEL,
            repetitions=repetitions,
            samples=tuple(samples),
        )


def save_benchmark_report(
    summary: BusinessLabBenchmarkSummary,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"business_lab_benchmark_{timestamp}.json"
    csv_path = output_dir / f"business_lab_benchmark_{timestamp}.csv"

    json_path.write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                "scenario_id",
                "repetition",
                "ok",
                "elapsed_ms",
                "action",
                "driver",
                "message",
            ),
        )
        writer.writeheader()
        for sample in summary.samples:
            writer.writerow(
                {
                    "scenario_id": sample.scenario_id,
                    "repetition": sample.repetition,
                    "ok": sample.ok,
                    "elapsed_ms": round(sample.elapsed_ms, 3),
                    "action": sample.action,
                    "driver": sample.driver or "",
                    "message": sample.message,
                }
            )

    return json_path, csv_path


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
