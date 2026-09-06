from __future__ import annotations

import json
import zipfile

from atlas.integrations.business_lab.demo_pack import (
    DEMO_PACK_LABEL,
    create_demo_pack,
    find_demo_sources,
    format_demo_readme,
)


def test_find_demo_sources_uses_latest_files_by_name(tmp_path) -> None:
    _write_demo_sources(tmp_path, stamp="20260905_010000")
    expected = _write_demo_sources(tmp_path, stamp="20260905_020000")

    sources = find_demo_sources(input_dir=tmp_path)

    assert sources["benchmark_json"] == expected["benchmark_json"]
    assert sources["executive_html"] == expected["executive_html"]


def test_create_demo_pack_copies_reports_and_zip(tmp_path) -> None:
    _write_demo_sources(tmp_path)

    result = create_demo_pack(input_dir=tmp_path, output_dir=tmp_path)

    assert result.folder_path.exists()
    assert result.zip_path.exists()
    assert result.manifest_path.exists()
    assert (result.folder_path / "01_relatorio_executivo.html").exists()
    assert (result.folder_path / "LEIA_ME.md").exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["provenance"] == DEMO_PACK_LABEL
    assert manifest["evidence"]["official_answers_used"] is False
    assert manifest["evidence"]["scenario_endpoint_used"] is False
    assert manifest["evidence"]["customer_claim"] is False


def test_demo_pack_zip_contains_expected_files(tmp_path) -> None:
    _write_demo_sources(tmp_path)

    result = create_demo_pack(input_dir=tmp_path, output_dir=tmp_path)

    with zipfile.ZipFile(result.zip_path) as zip_file:
        names = set(zip_file.namelist())

    assert "01_relatorio_executivo.html" in names
    assert "04_relatorio_valor.csv" in names
    assert "05_benchmark_medido.json" in names
    assert "MANIFESTO_DEMO.json" in names
    assert "LEIA_ME.md" in names


def test_format_demo_readme_contains_commercial_disclaimer(tmp_path) -> None:
    sources = _write_demo_sources(tmp_path)
    executive_payload = json.loads(
        sources["executive_json"].read_text(encoding="utf-8")
    )
    manifest = {
        "provenance": DEMO_PACK_LABEL,
        "company_name": "Nexyra",
        "product_name": "Atlas",
        "client_segment": "escola técnica",
        "metrics": executive_payload["metrics"],
        "pack_files": {"executive_html": "01_relatorio_executivo.html"},
        "honest_disclaimer": "Não apresentar como resultado real de cliente.",
    }

    readme = format_demo_readme(manifest)

    assert "Demo Pack" in readme
    assert "Sucesso operacional" in readme
    assert "Não apresentar como resultado real de cliente" in readme


def test_missing_sources_raise_clear_error(tmp_path) -> None:
    try:
        find_demo_sources(input_dir=tmp_path)
    except FileNotFoundError as error:
        assert "business_lab_benchmark_*.json" in str(error)
    else:
        raise AssertionError("Fonte ausente deveria gerar FileNotFoundError")


def _write_demo_sources(
    tmp_path,
    *,
    stamp: str = "20260905_010000",
) -> dict[str, object]:
    benchmark_json = tmp_path / f"business_lab_benchmark_{stamp}.json"
    value_json = tmp_path / f"business_lab_value_report_{stamp}.json"
    value_csv = tmp_path / f"business_lab_value_report_{stamp}.csv"
    value_md = tmp_path / f"business_lab_value_report_{stamp}.md"
    executive_json = tmp_path / f"business_lab_executive_report_{stamp}.json"
    executive_md = tmp_path / f"business_lab_executive_report_{stamp}.md"
    executive_html = tmp_path / f"business_lab_executive_report_{stamp}.html"

    benchmark_json.write_text(
        json.dumps({"total": 10, "passed": 10, "failed": 0}),
        encoding="utf-8",
    )
    value_payload = {
        "total_scenarios": 10,
        "source_provenance": "MEASURED_IN_LOCAL_BUSINESS_LAB",
        "report_provenance": "MEASURED_ATLAS_PLUS_ESTIMATED_MANUAL_BASELINE",
    }
    value_json.write_text(json.dumps(value_payload), encoding="utf-8")
    value_csv.write_text("scenario_id,ok\nLAB-001,True\n", encoding="utf-8")
    value_md.write_text("# Relatório de Valor\n", encoding="utf-8")
    executive_json.write_text(
        json.dumps(_executive_payload()),
        encoding="utf-8",
    )
    executive_md.write_text("# Relatório Executivo\n", encoding="utf-8")
    executive_html.write_text("<!doctype html><h1>Atlas</h1>", encoding="utf-8")
    return {
        "benchmark_json": benchmark_json,
        "value_json": value_json,
        "value_csv": value_csv,
        "value_md": value_md,
        "executive_json": executive_json,
        "executive_md": executive_md,
        "executive_html": executive_html,
    }


def _executive_payload() -> dict[str, object]:
    return {
        "metrics": {
            "success_rate_percent": 100.0,
            "reduction_percent": 95.0,
            "total_saved_minutes": 20.0,
            "monthly_saved_hours": 33.33,
            "monthly_estimated_value_brl": 833.25,
        },
        "evidence": {
            "atlas_source": "MEASURED_IN_LOCAL_BUSINESS_LAB",
            "manual_baseline": "ESTIMATED_MANUAL_BASELINE",
            "value_report_source": "MEASURED_ATLAS_PLUS_ESTIMATED_MANUAL_BASELINE",
            "official_answers_used": False,
            "scenario_endpoint_used": False,
        },
    }
