from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .benchmark_runner import DEFAULT_OUTPUT_DIR
from .lab_runner import LAB_SEQUENCE, LAB_TITLES
from .value_report import load_latest_benchmark

PILOT_COMPARISON_LABEL = "MEASURED_ATLAS_PLUS_MANUAL_PILOT_COMPARISON"
MANUAL_PILOT_LABEL = "MANUAL_PILOT_MEASUREMENTS"
TEMPLATE_FILENAME = "business_lab_manual_pilot_template.csv"


@dataclass(frozen=True, slots=True)
class ManualPilotSample:
    scenario_id: str
    sample_id: str
    elapsed_seconds: float
    operator: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "sample_id": self.sample_id,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "operator": self.operator,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ScenarioPilotComparison:
    scenario_id: str
    title: str
    atlas_ok: bool
    manual_samples_count: int
    atlas_samples_count: int
    manual_average_seconds: float
    atlas_average_seconds: float
    saved_seconds: float
    reduction_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "atlas_ok": self.atlas_ok,
            "manual_samples_count": self.manual_samples_count,
            "atlas_samples_count": self.atlas_samples_count,
            "manual_average_seconds": round(self.manual_average_seconds, 3),
            "atlas_average_seconds": round(self.atlas_average_seconds, 3),
            "saved_seconds": round(self.saved_seconds, 3),
            "reduction_percent": round(self.reduction_percent, 2),
        }


@dataclass(frozen=True, slots=True)
class BusinessLabPilotComparisonReport:
    generated_at: str
    source_benchmark_file: str
    source_manual_file: str
    provenance: str
    manual_source_kind: str
    hourly_cost_brl: float
    monthly_runs: int
    comparisons: tuple[ScenarioPilotComparison, ...] = field(default_factory=tuple)

    @property
    def total_scenarios(self) -> int:
        return len(self.comparisons)

    @property
    def passed_scenarios(self) -> int:
        return sum(1 for item in self.comparisons if item.atlas_ok)

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
        return round(sum(item.manual_average_seconds for item in self.comparisons), 3)

    @property
    def total_atlas_seconds(self) -> float:
        return round(sum(item.atlas_average_seconds for item in self.comparisons), 3)

    @property
    def total_saved_seconds(self) -> float:
        return round(sum(item.saved_seconds for item in self.comparisons), 3)

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
            "source_manual_file": self.source_manual_file,
            "provenance": self.provenance,
            "manual_source_kind": self.manual_source_kind,
            "hourly_cost_brl": round(self.hourly_cost_brl, 2),
            "monthly_runs": self.monthly_runs,
            "total_scenarios": self.total_scenarios,
            "passed_scenarios": self.passed_scenarios,
            "failed_scenarios": self.failed_scenarios,
            "success_rate_percent": self.success_rate_percent,
            "total_manual_seconds": self.total_manual_seconds,
            "total_atlas_seconds": self.total_atlas_seconds,
            "total_saved_seconds": self.total_saved_seconds,
            "total_saved_minutes": self.total_saved_minutes,
            "total_saved_hours": self.total_saved_hours,
            "reduction_percent": self.reduction_percent,
            "monthly_saved_hours": self.monthly_saved_hours,
            "monthly_estimated_value_brl": self.monthly_estimated_value_brl,
            "comparisons": [item.to_dict() for item in self.comparisons],
        }


def create_manual_template(*, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    """Cria uma planilha-modelo para medir a execução humana dos LABs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / TEMPLATE_FILENAME
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                "scenario_id",
                "sample_id",
                "elapsed_seconds",
                "operator",
                "notes",
            ),
        )
        writer.writeheader()
        for scenario_id in LAB_SEQUENCE:
            writer.writerow(
                {
                    "scenario_id": scenario_id,
                    "sample_id": "manual-001",
                    "elapsed_seconds": "",
                    "operator": "",
                    "notes": LAB_TITLES.get(scenario_id, scenario_id),
                }
            )
    return path


def load_manual_samples(path: Path) -> tuple[ManualPilotSample, ...]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo manual não encontrado: {path}")

    samples: list[ManualPilotSample] = []
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for line_number, row in enumerate(reader, start=2):
            scenario_id = str(row.get("scenario_id") or "").strip().upper()
            if not scenario_id:
                continue
            if scenario_id not in LAB_SEQUENCE:
                raise ValueError(
                    f"Cenário inválido na linha {line_number}: {scenario_id}."
                )

            elapsed_raw = str(row.get("elapsed_seconds") or "").strip()
            if not elapsed_raw:
                continue
            elapsed_seconds = float(elapsed_raw.replace(",", "."))
            if elapsed_seconds < 0:
                raise ValueError(
                    f"Tempo manual negativo na linha {line_number}: {elapsed_raw}."
                )

            samples.append(
                ManualPilotSample(
                    scenario_id=scenario_id,
                    sample_id=str(row.get("sample_id") or f"linha-{line_number}").strip(),
                    elapsed_seconds=elapsed_seconds,
                    operator=str(row.get("operator") or "").strip(),
                    notes=str(row.get("notes") or "").strip(),
                )
            )

    if not samples:
        raise ValueError(
            "Nenhuma medição manual válida encontrada. Preencha elapsed_seconds."
        )
    return tuple(samples)


def build_pilot_comparison_from_files(
    *,
    manual_csv_path: Path,
    benchmark_json_path: Path | None = None,
    input_dir: Path = DEFAULT_OUTPUT_DIR,
    hourly_cost_brl: float = 0.0,
    monthly_runs: int = 1,
) -> BusinessLabPilotComparisonReport:
    benchmark_path = benchmark_json_path or load_latest_benchmark(input_dir=input_dir)
    benchmark_payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    manual_samples = load_manual_samples(manual_csv_path)
    return build_pilot_comparison(
        benchmark_payload,
        manual_samples,
        source_benchmark_file=str(benchmark_path),
        source_manual_file=str(manual_csv_path),
        hourly_cost_brl=hourly_cost_brl,
        monthly_runs=monthly_runs,
    )


def build_pilot_comparison(
    benchmark_payload: dict[str, Any],
    manual_samples: tuple[ManualPilotSample, ...],
    *,
    source_benchmark_file: str = "<memory>",
    source_manual_file: str = "<memory>",
    hourly_cost_brl: float = 0.0,
    monthly_runs: int = 1,
) -> BusinessLabPilotComparisonReport:
    if hourly_cost_brl < 0:
        raise ValueError("hourly_cost_brl não pode ser negativo.")
    if monthly_runs < 1:
        raise ValueError("monthly_runs precisa ser maior ou igual a 1.")

    manual_by_scenario = _manual_samples_by_scenario(manual_samples)
    atlas_by_scenario = _atlas_samples_by_scenario(benchmark_payload.get("samples"))
    comparisons: list[ScenarioPilotComparison] = []

    for scenario_id in LAB_SEQUENCE:
        scenario_manual = manual_by_scenario.get(scenario_id, [])
        scenario_atlas = atlas_by_scenario.get(scenario_id, [])
        if not scenario_manual or not scenario_atlas:
            continue

        manual_average = _average(sample.elapsed_seconds for sample in scenario_manual)
        atlas_average = _average(
            float(sample.get("elapsed_ms") or 0.0) / 1000
            for sample in scenario_atlas
        )
        saved_seconds = max(0.0, manual_average - atlas_average)
        reduction_percent = (
            (saved_seconds / manual_average) * 100 if manual_average > 0 else 0.0
        )

        comparisons.append(
            ScenarioPilotComparison(
                scenario_id=scenario_id,
                title=LAB_TITLES.get(scenario_id, scenario_id),
                atlas_ok=all(bool(sample.get("ok")) for sample in scenario_atlas),
                manual_samples_count=len(scenario_manual),
                atlas_samples_count=len(scenario_atlas),
                manual_average_seconds=manual_average,
                atlas_average_seconds=atlas_average,
                saved_seconds=saved_seconds,
                reduction_percent=reduction_percent,
            )
        )

    if not comparisons:
        raise ValueError(
            "Não houve cenários em comum entre o CSV manual e o benchmark do Atlas."
        )

    return BusinessLabPilotComparisonReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        source_benchmark_file=source_benchmark_file,
        source_manual_file=source_manual_file,
        provenance=PILOT_COMPARISON_LABEL,
        manual_source_kind=MANUAL_PILOT_LABEL,
        hourly_cost_brl=hourly_cost_brl,
        monthly_runs=monthly_runs,
        comparisons=tuple(comparisons),
    )


def save_pilot_comparison_report(
    report: BusinessLabPilotComparisonReport,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"business_lab_pilot_comparison_{timestamp}.json"
    csv_path = output_dir / f"business_lab_pilot_comparison_{timestamp}.csv"
    md_path = output_dir / f"business_lab_pilot_comparison_{timestamp}.md"

    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_path.write_text(_to_csv(report), encoding="utf-8")
    md_path.write_text(format_pilot_comparison_markdown(report), encoding="utf-8")
    return json_path, csv_path, md_path


def format_pilot_comparison_markdown(
    report: BusinessLabPilotComparisonReport,
) -> str:
    lines = [
        "# Atlas x Operação Manual Medida — Business Lab",
        "",
        "## Resumo",
        "",
        f"- Origem: `{report.provenance}`",
        f"- Medição manual: `{report.manual_source_kind}`",
        f"- Cenários comparados: {report.total_scenarios}",
        f"- Sucesso operacional Atlas: {report.success_rate_percent:.2f}%",
        f"- Tempo manual médio somado: {report.total_manual_seconds:.2f}s",
        f"- Tempo Atlas médio somado: {report.total_atlas_seconds:.2f}s",
        f"- Economia por ciclo: {report.total_saved_minutes:.2f} min",
        f"- Redução medida: {report.reduction_percent:.2f}%",
    ]

    if report.hourly_cost_brl > 0:
        lines.extend(
            [
                f"- Execuções mensais: {report.monthly_runs}",
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
            "## Comparação por cenário",
            "",
            (
                "| Cenário | Status Atlas | Amostras manual | Amostras Atlas | "
                "Manual médio | Atlas médio | Economia | Redução |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )

    for item in report.comparisons:
        status = "OK" if item.atlas_ok else "FALHA"
        lines.append(
            "| "
            f"{item.scenario_id} - {item.title} | "
            f"{status} | "
            f"{item.manual_samples_count} | "
            f"{item.atlas_samples_count} | "
            f"{item.manual_average_seconds:.2f}s | "
            f"{item.atlas_average_seconds:.2f}s | "
            f"{item.saved_seconds:.2f}s | "
            f"{item.reduction_percent:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Aviso de uso",
            "",
            (
                "Este relatório compara o tempo real medido do Atlas com tempos "
                "manuais preenchidos em CSV. Ainda usa o Business Lab e dados "
                "sintéticos; para virar case real, repetir o protocolo em um "
                "cliente ou piloto supervisionado."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _manual_samples_by_scenario(
    samples: tuple[ManualPilotSample, ...],
) -> dict[str, list[ManualPilotSample]]:
    grouped: dict[str, list[ManualPilotSample]] = {}
    for sample in samples:
        grouped.setdefault(sample.scenario_id, []).append(sample)
    return grouped


def _atlas_samples_by_scenario(raw_samples: Any) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(raw_samples, list):
        return grouped
    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        scenario_id = str(sample.get("scenario_id") or "").strip().upper()
        if scenario_id in LAB_SEQUENCE:
            grouped.setdefault(scenario_id, []).append(sample)
    return grouped


def _average(values: Any) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 3)


def _to_csv(report: BusinessLabPilotComparisonReport) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=(
            "scenario_id",
            "title",
            "atlas_ok",
            "manual_samples_count",
            "atlas_samples_count",
            "manual_average_seconds",
            "atlas_average_seconds",
            "saved_seconds",
            "reduction_percent",
        ),
    )
    writer.writeheader()
    for item in report.comparisons:
        writer.writerow(item.to_dict())
    return buffer.getvalue()
