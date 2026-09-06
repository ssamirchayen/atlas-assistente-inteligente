from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.integrations.business_lab.lab_runner import LAB_SEQUENCE
from atlas.integrations.business_lab.pilot_comparison import (
    ManualPilotSample,
    build_pilot_comparison,
    build_pilot_comparison_from_files,
    create_manual_template,
    load_manual_samples,
    save_pilot_comparison_report,
)


def test_create_manual_template(tmp_path: Path) -> None:
    path = create_manual_template(output_dir=tmp_path)

    content = path.read_text(encoding="utf-8")

    assert path.exists()
    assert "scenario_id,sample_id,elapsed_seconds,operator,notes" in content
    assert "LAB-001" in content
    assert "LAB-010" in content


def test_load_manual_samples(tmp_path: Path) -> None:
    path = tmp_path / "manual.csv"
    path.write_text(
        "scenario_id,sample_id,elapsed_seconds,operator,notes\n"
        "LAB-001,manual-001,60,Ssamir,teste\n"
        "LAB-001,manual-002,90,Ssamir,teste\n",
        encoding="utf-8",
    )

    samples = load_manual_samples(path)

    assert len(samples) == 2
    assert samples[0].scenario_id == "LAB-001"
    assert samples[1].elapsed_seconds == 90


def test_load_manual_samples_rejects_invalid_scenario(tmp_path: Path) -> None:
    path = tmp_path / "manual.csv"
    path.write_text(
        "scenario_id,sample_id,elapsed_seconds,operator,notes\n"
        "LAB-999,manual-001,60,Ssamir,teste\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Cenário inválido"):
        load_manual_samples(path)


def test_build_pilot_comparison_from_payload() -> None:
    benchmark = _benchmark_payload()
    samples = tuple(
        ManualPilotSample(
            scenario_id=scenario_id,
            sample_id="manual-001",
            elapsed_seconds=30.0,
        )
        for scenario_id in LAB_SEQUENCE
    )

    report = build_pilot_comparison(
        benchmark,
        samples,
        hourly_cost_brl=25.0,
        monthly_runs=100,
    )

    assert report.total_scenarios == 10
    assert report.success_rate_percent == 100.0
    assert report.reduction_percent > 0
    assert report.monthly_estimated_value_brl > 0
    assert report.comparisons[0].manual_average_seconds == 30.0
    assert report.comparisons[0].atlas_average_seconds == 1.0


def test_build_pilot_comparison_from_files(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "business_lab_benchmark_001.json"
    benchmark_path.write_text(
        json.dumps(_benchmark_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    manual_path = tmp_path / "manual.csv"
    manual_path.write_text(
        "scenario_id,sample_id,elapsed_seconds,operator,notes\n"
        "LAB-001,manual-001,60,Ssamir,teste\n",
        encoding="utf-8",
    )

    report = build_pilot_comparison_from_files(
        manual_csv_path=manual_path,
        benchmark_json_path=benchmark_path,
    )

    assert report.total_scenarios == 1
    assert report.source_benchmark_file == str(benchmark_path)
    assert report.source_manual_file == str(manual_path)


def test_save_pilot_comparison_report(tmp_path: Path) -> None:
    report = build_pilot_comparison(
        _benchmark_payload(),
        (ManualPilotSample("LAB-001", "manual-001", 60.0),),
    )

    json_path, csv_path, md_path = save_pilot_comparison_report(
        report,
        output_dir=tmp_path,
    )

    assert json_path.exists()
    assert csv_path.exists()
    assert md_path.exists()
    assert "Atlas x Operação Manual Medida" in md_path.read_text(encoding="utf-8")


def _benchmark_payload() -> dict[str, object]:
    return {
        "provenance": "MEASURED_IN_LOCAL_BUSINESS_LAB",
        "samples": [
            {
                "scenario_id": scenario_id,
                "repetition": 1,
                "ok": True,
                "elapsed_ms": 1000.0,
                "action": "test",
                "driver": "api",
                "message": "ok",
            }
            for scenario_id in LAB_SEQUENCE
        ],
    }
