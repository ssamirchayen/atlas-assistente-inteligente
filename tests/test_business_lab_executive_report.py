from __future__ import annotations

import json

from atlas.integrations.business_lab.executive_report import (
    EXECUTIVE_REPORT_LABEL,
    build_executive_report,
    build_executive_report_from_file,
    format_executive_html,
    format_executive_markdown,
    load_latest_value_report,
    save_executive_report,
)


def test_build_executive_report_keeps_honest_evidence_labels() -> None:
    report = build_executive_report(_sample_value_payload())

    assert report["report_provenance"] == EXECUTIVE_REPORT_LABEL
    assert report["status"] == "aprovado"
    assert report["evidence"]["official_answers_used"] is False
    assert report["evidence"]["scenario_endpoint_used"] is False
    assert report["metrics"]["success_rate_percent"] == 100.0


def test_markdown_contains_commercial_sections_and_disclaimer() -> None:
    report = build_executive_report(_sample_value_payload())
    markdown = format_executive_markdown(report)

    assert "Relatório Executivo" in markdown
    assert "Indicadores principais" in markdown
    assert "Limitações honestas" in markdown
    assert "não como resultado real de cliente" in markdown
    assert "Gabaritos oficiais usados: não" in markdown


def test_html_contains_cards_and_escaped_content() -> None:
    payload = _sample_value_payload()
    report = build_executive_report(
        payload,
        company_name="Nexyra <Lab>",
    )
    html = format_executive_html(report)

    assert "<!doctype html>" in html
    assert "Nexyra &lt;Lab&gt;" in html
    assert "Potencial/mês" in html


def test_save_executive_report_creates_json_markdown_and_html(tmp_path) -> None:
    report = build_executive_report(_sample_value_payload())
    files = save_executive_report(report, output_dir=tmp_path)

    assert files.json_path.exists()
    assert files.markdown_path.exists()
    assert files.html_path.exists()
    assert files.json_path.name.startswith("business_lab_executive_report_")


def test_build_from_file_and_load_latest_value_report(tmp_path) -> None:
    older = tmp_path / "business_lab_value_report_20260905_010000.json"
    newer = tmp_path / "business_lab_value_report_20260905_020000.json"
    older.write_text(json.dumps(_sample_value_payload()), encoding="utf-8")
    newer.write_text(json.dumps(_sample_value_payload()), encoding="utf-8")

    latest = load_latest_value_report(input_dir=tmp_path)
    report = build_executive_report_from_file(latest)

    assert latest == newer
    assert report["metrics"]["total_scenarios"] == 3


def _sample_value_payload() -> dict[str, object]:
    return {
        "source_provenance": "MEASURED_IN_LOCAL_BUSINESS_LAB",
        "report_provenance": "MEASURED_ATLAS_PLUS_ESTIMATED_MANUAL_BASELINE",
        "manual_baseline_kind": "ESTIMATED_MANUAL_BASELINE",
        "total_scenarios": 3,
        "passed_scenarios": 3,
        "failed_scenarios": 0,
        "success_rate_percent": 100.0,
        "total_manual_minutes": 7.5,
        "total_atlas_minutes": 0.5,
        "total_saved_minutes": 7.0,
        "reduction_percent": 93.33,
        "monthly_runs": 100,
        "hourly_cost_brl": 25.0,
        "monthly_saved_hours": 11.6667,
        "monthly_estimated_value_brl": 291.67,
        "comparisons": [
            {
                "scenario_id": "LAB-001",
                "title": "Localizar lead por código",
                "ok": True,
                "manual_baseline_seconds": 90.0,
                "atlas_average_seconds": 1.2,
                "saved_seconds": 88.8,
                "reduction_percent": 98.67,
            },
            {
                "scenario_id": "LAB-002",
                "title": "Filtrar leads de Radiologia com prioridade alta",
                "ok": True,
                "manual_baseline_seconds": 240.0,
                "atlas_average_seconds": 2.4,
                "saved_seconds": 237.6,
                "reduction_percent": 99.0,
            },
            {
                "scenario_id": "LAB-003",
                "title": "Consultar atendimentos do lead",
                "ok": True,
                "manual_baseline_seconds": 120.0,
                "atlas_average_seconds": 1.8,
                "saved_seconds": 118.2,
                "reduction_percent": 98.5,
            },
        ],
    }
