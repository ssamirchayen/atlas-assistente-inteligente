from __future__ import annotations

import json
from pathlib import Path

from atlas.integrations.business_lab.benchmark_runner import PROVENANCE_LABEL
from atlas.integrations.business_lab.value_report import (
    MANUAL_BASELINE_LABEL,
    VALUE_REPORT_LABEL,
    build_value_report,
    build_value_report_from_file,
    load_latest_benchmark,
    save_value_report,
)


def _payload() -> dict[str, object]:
    return {
        "provenance": PROVENANCE_LABEL,
        "samples": [
            {
                "scenario_id": "LAB-001",
                "repetition": 1,
                "ok": True,
                "elapsed_ms": 1000.0,
            },
            {
                "scenario_id": "LAB-001",
                "repetition": 2,
                "ok": True,
                "elapsed_ms": 2000.0,
            },
            {
                "scenario_id": "LAB-002",
                "repetition": 1,
                "ok": True,
                "elapsed_ms": 3000.0,
            },
        ],
    }


def test_build_value_report_compares_measured_atlas_with_manual_baseline() -> None:
    report = build_value_report(
        _payload(),
        hourly_cost_brl=25.0,
        monthly_runs=30,
    )

    assert report.report_provenance == VALUE_REPORT_LABEL
    assert report.manual_baseline_kind == MANUAL_BASELINE_LABEL
    assert report.source_provenance == PROVENANCE_LABEL
    assert report.total_scenarios == 2
    assert report.passed_scenarios == 2
    assert report.success_rate_percent == 100.0
    assert report.total_manual_seconds == 330.0
    assert report.total_atlas_seconds == 4.5
    assert report.total_saved_seconds == 325.5
    assert report.monthly_estimated_value_brl > 0

    lab001 = report.comparisons[0]
    assert lab001.scenario_id == "LAB-001"
    assert lab001.samples_count == 2
    assert lab001.atlas_average_seconds == 1.5


def test_build_value_report_marks_failed_scenario() -> None:
    payload = {
        "provenance": PROVENANCE_LABEL,
        "samples": [
            {
                "scenario_id": "LAB-001",
                "repetition": 1,
                "ok": False,
                "elapsed_ms": 500.0,
            }
        ],
    }

    report = build_value_report(payload)

    assert report.total_scenarios == 1
    assert report.passed_scenarios == 0
    assert report.failed_scenarios == 1
    assert report.success_rate_percent == 0.0


def test_save_value_report_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    report = build_value_report(_payload())

    json_path, csv_path, md_path = save_value_report(report, output_dir=tmp_path)

    assert json_path.exists()
    assert csv_path.exists()
    assert md_path.exists()

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["report_provenance"] == VALUE_REPORT_LABEL
    assert "LAB-001" in csv_path.read_text(encoding="utf-8")
    markdown = md_path.read_text(encoding="utf-8")
    assert "Atlas x Operação Manual" in markdown
    assert MANUAL_BASELINE_LABEL in markdown


def test_build_value_report_from_file(tmp_path: Path) -> None:
    source = tmp_path / "business_lab_benchmark_20260905_000001.json"
    source.write_text(json.dumps(_payload()), encoding="utf-8")

    report = build_value_report_from_file(source)

    assert report.source_benchmark_file == str(source)
    assert report.total_scenarios == 2


def test_load_latest_benchmark_uses_most_recent_file(tmp_path: Path) -> None:
    older = tmp_path / "business_lab_benchmark_20260905_000001.json"
    newer = tmp_path / "business_lab_benchmark_20260905_000002.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")

    latest = load_latest_benchmark(input_dir=tmp_path)

    assert latest in {older, newer}
    assert latest.name.startswith("business_lab_benchmark_")
