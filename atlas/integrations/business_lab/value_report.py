from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .benchmark_runner import DEFAULT_OUTPUT_DIR, PROVENANCE_LABEL
from .lab_runner import LAB_SEQUENCE, LAB_TITLES

MANUAL_BASELINE_LABEL = "ESTIMATED_MANUAL_BASELINE"
VALUE_REPORT_LABEL = "MEASURED_ATLAS_PLUS_ESTIMATED_MANUAL_BASELINE"

MANUAL_BASELINE_SECONDS = {
    "LAB-001": 90.0,
    "LAB-002": 240.0,
    "LAB-003": 120.0,
    "LAB-004": 90.0,
    "LAB-005": 90.0,
    "LAB-006": 180.0,
    "LAB-007": 120.0,
    "LAB-008": 240.0,
    "LAB-009": 180.0,
    "LAB-010": 60.0,
}


@dataclass(frozen=True, slots=True)
class ScenarioValueComparison:
    scenario_id: str
    title: str
    ok: bool
    samples_count: int
    manual_baseline_seconds: float
    atlas_average_seconds: float
    saved_seconds: float
    reduction_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "ok": self.ok,
            "samples_count": self.samples_count,
            "manual_baseline_seconds": round(self.manual_baseline_seconds, 3),
            "atlas_average_seconds": round(self.atlas_average_seconds, 3),
            "saved_seconds": round(self.saved_seconds, 3),
            "reduction_percent": round(self.reduction_percent, 2),
        }


@dataclass(frozen=True, slots=True)
class BusinessLabValueReport:
    generated_at: str
    source_benchmark_file: str
    source_provenance: str
    report_provenance: str
    manual_baseline_kind: str
    hourly_cost_brl: float
    monthly_runs: int
    comparisons: tuple[ScenarioValueComparison, ...] = field(default_factory=tuple)

    @property
    def total_scenarios(self) -> int:
        return len(self.comparisons)

    @property
    def passed_scenarios(self) -> int:
        return sum(1 for item in self.comparisons if item.ok)

    @property
    def failed_scenarios(self) -> int:
        return self.total_scenarios - self.passed_scenarios

    @property
    def success_rate_percent(self) -> float:
        if self.total_scenarios == 0:
            return 0.0
        return round((self.passed_scenarios / self.total_scenarios) * 100, 2)

    @property
    def total_manual_seconds(self) -> float:
        return round(sum(item.manual_baseline_seconds for item in self.comparisons), 3)

    @property
    def total_atlas_seconds(self) -> float:
        return round(sum(item.atlas_average_seconds for item in self.comparisons), 3)

    @property
    def total_saved_seconds(self) -> float:
        return round(sum(item.saved_seconds for item in self.comparisons), 3)

    @property
    def total_manual_minutes(self) -> float:
        return round(self.total_manual_seconds / 60, 2)

    @property
    def total_atlas_minutes(self) -> float:
        return round(self.total_atlas_seconds / 60, 2)

    @property
    def total_saved_minutes(self) -> float:
        return round(self.total_saved_seconds / 60, 2)

    @property
    def total_saved_hours(self) -> float:
        return round(self.total_saved_seconds / 3600, 4)

    @property
    def reduction_percent(self) -> float:
        if self.total_manual_seconds <= 0:
            return 0.0
        return round((self.total_saved_seconds / self.total_manual_seconds) * 100, 2)

    @property
    def monthly_saved_hours(self) -> float:
        return round(self.total_saved_hours * self.monthly_runs, 4)

    @property
    def monthly_estimated_value_brl(self) -> float:
        return round(self.monthly_saved_hours * self.hourly_cost_brl, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "source_benchmark_file": self.source_benchmark_file,
            "source_provenance": self.source_provenance,
            "report_provenance": self.report_provenance,
            "manual_baseline_kind": self.manual_baseline_kind,
            "hourly_cost_brl": round(self.hourly_cost_brl, 2),
            "monthly_runs": self.monthly_runs,
            "total_scenarios": self.total_scenarios,
            "passed_scenarios": self.passed_scenarios,
            "failed_scenarios": self.failed_scenarios,
            "success_rate_percent": self.success_rate_percent,
            "total_manual_seconds": self.total_manual_seconds,
            "total_atlas_seconds": self.total_atlas_seconds,
            "total_saved_seconds": self.total_saved_seconds,
            "total_manual_minutes": self.total_manual_minutes,
            "total_atlas_minutes": self.total_atlas_minutes,
            "total_saved_minutes": self.total_saved_minutes,
            "total_saved_hours": self.total_saved_hours,
            "reduction_percent": self.reduction_percent,
            "monthly_saved_hours": self.monthly_saved_hours,
            "monthly_estimated_value_brl": self.monthly_estimated_value_brl,
            "comparisons": [item.to_dict() for item in self.comparisons],
        }


def load_latest_benchmark(
    *,
    input_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    candidates = sorted(input_dir.glob("business_lab_benchmark_*.json"))
    if not candidates:
        raise FileNotFoundError(
            "Nenhum benchmark JSON encontrado. Rode primeiro "
            "tools/run_business_lab_benchmark.py."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_value_report_from_file(
    benchmark_json_path: Path,
    *,
    hourly_cost_brl: float = 0.0,
    monthly_runs: int = 1,
) -> BusinessLabValueReport:
    payload = json.loads(benchmark_json_path.read_text(encoding="utf-8"))
    return build_value_report(
        payload,
        source_benchmark_file=str(benchmark_json_path),
        hourly_cost_brl=hourly_cost_brl,
        monthly_runs=monthly_runs,
    )


def build_value_report(
    benchmark_payload: dict[str, Any],
    *,
    source_benchmark_file: str = "<memory>",
    hourly_cost_brl: float = 0.0,
    monthly_runs: int = 1,
) -> BusinessLabValueReport:
    if hourly_cost_brl < 0:
        raise ValueError("hourly_cost_brl não pode ser negativo.")
    if monthly_runs < 1:
        raise ValueError("monthly_runs precisa ser maior ou igual a 1.")

    source_provenance = str(benchmark_payload.get("provenance") or "")
    samples = _samples_by_scenario(benchmark_payload.get("samples"))
    comparisons: list[ScenarioValueComparison] = []

    for scenario_id in LAB_SEQUENCE:
        scenario_samples = samples.get(scenario_id, [])
        if not scenario_samples:
            continue

        atlas_seconds = _average(
            float(sample.get("elapsed_ms") or 0.0) / 1000
            for sample in scenario_samples
        )
        manual_seconds = MANUAL_BASELINE_SECONDS[scenario_id]
        saved_seconds = max(0.0, manual_seconds - atlas_seconds)
        reduction_percent = (
            (saved_seconds / manual_seconds) * 100 if manual_seconds > 0 else 0.0
        )

        comparisons.append(
            ScenarioValueComparison(
                scenario_id=scenario_id,
                title=LAB_TITLES.get(scenario_id, scenario_id),
                ok=all(bool(sample.get("ok")) for sample in scenario_samples),
                samples_count=len(scenario_samples),
                manual_baseline_seconds=manual_seconds,
                atlas_average_seconds=atlas_seconds,
                saved_seconds=saved_seconds,
                reduction_percent=reduction_percent,
            )
        )

    return BusinessLabValueReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_benchmark_file=source_benchmark_file,
        source_provenance=source_provenance or PROVENANCE_LABEL,
        report_provenance=VALUE_REPORT_LABEL,
        manual_baseline_kind=MANUAL_BASELINE_LABEL,
        hourly_cost_brl=hourly_cost_brl,
        monthly_runs=monthly_runs,
        comparisons=tuple(comparisons),
    )


def save_value_report(
    report: BusinessLabValueReport,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"business_lab_value_report_{timestamp}.json"
    csv_path = output_dir / f"business_lab_value_report_{timestamp}.csv"
    md_path = output_dir / f"business_lab_value_report_{timestamp}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_path.write_text(_to_csv(report), encoding="utf-8")
    md_path.write_text(format_value_report_markdown(report), encoding="utf-8")

    return json_path, csv_path, md_path


def format_value_report_markdown(report: BusinessLabValueReport) -> str:
    lines = [
        "# Atlas x Operação Manual — Business Lab",
        "",
        "## Resumo executivo",
        "",
        f"- Fonte Atlas: `{report.source_provenance}`",
        f"- Baseline manual: `{report.manual_baseline_kind}`",
        f"- Cenários analisados: {report.total_scenarios}",
        f"- Sucesso operacional: {report.success_rate_percent:.2f}%",
        f"- Tempo manual estimado: {report.total_manual_minutes:.2f} min",
        f"- Tempo médio Atlas medido: {report.total_atlas_minutes:.2f} min",
        f"- Tempo economizado por ciclo: {report.total_saved_minutes:.2f} min",
        f"- Redução estimada: {report.reduction_percent:.2f}%",
    ]

    if report.hourly_cost_brl > 0:
        lines.extend(
            [
                f"- Execuções mensais informadas: {report.monthly_runs}",
                f"- Horas economizadas/mês: {report.monthly_saved_hours:.2f}h",
                (
                    "- Valor potencial/mês: "
                    f"R$ {report.monthly_estimated_value_brl:.2f}"
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Comparativo por cenário",
            "",
            (
                "| Cenário | Status | Manual estimado | Atlas medido | "
                "Economia | Redução |"
            ),
            "|---|---:|---:|---:|---:|---:|",
        ]
    )

    for item in report.comparisons:
        status = "OK" if item.ok else "FALHA"
        lines.append(
            "| "
            f"{item.scenario_id} - {item.title} | "
            f"{status} | "
            f"{item.manual_baseline_seconds:.2f}s | "
            f"{item.atlas_average_seconds:.2f}s | "
            f"{item.saved_seconds:.2f}s | "
            f"{item.reduction_percent:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Observação de confiança",
            "",
            (
                "Este relatório mistura tempo real medido do Atlas no Business Lab "
                "com uma linha de base manual estimada. Ele não deve ser apresentado "
                "como ganho real de cliente sem validação humana em operação real."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _samples_by_scenario(raw_samples: Any) -> dict[str, list[dict[str, Any]]]:
    samples: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(raw_samples, list):
        return samples

    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        scenario_id = str(sample.get("scenario_id") or "").strip().upper()
        if scenario_id not in MANUAL_BASELINE_SECONDS:
            continue
        samples.setdefault(scenario_id, []).append(sample)

    return samples


def _average(values: Any) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 3)


def _to_csv(report: BusinessLabValueReport) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "scenario_id",
            "title",
            "ok",
            "samples_count",
            "manual_baseline_seconds",
            "atlas_average_seconds",
            "saved_seconds",
            "reduction_percent",
        ),
    )
    writer.writeheader()
    for item in report.comparisons:
        writer.writerow(item.to_dict())
    return buffer.getvalue()
