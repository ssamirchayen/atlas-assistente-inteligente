from __future__ import annotations

import json
import threading
from urllib.request import urlopen

from atlas.copilot.local_api import create_copilot_server
from atlas.copilot.models import CopilotResponse
from atlas.copilot.smart_reports import (
    SmartReportFilters,
    SmartReportResult,
    build_report_exports,
    save_report_bundle,
)


def _sample_report() -> SmartReportResult:
    return SmartReportResult(
        title="Relatório inteligente de teste",
        generated_at="2026-09-05T14:30:00",
        filters=SmartReportFilters(course_name="Radiologia"),
        metrics={"total_leads_reportado": 10, "matriculas_reportadas": 2},
        tables={"leads": [], "matriculas": [], "retornos": [], "atendimentos": []},
        insights=["Insight de teste"],
        alerts=["Alerta de teste"],
        next_steps=["Próximo passo de teste"],
        source_notes=["Fonte de teste"],
    )


def test_save_report_bundle_creates_download_files(tmp_path) -> None:
    report = _sample_report()
    exports = build_report_exports(report)

    files = save_report_bundle(report, exports, output_dir=tmp_path)

    assert files["base_filename"].startswith("business_lab_smart_report_")
    downloads = files["downloads"]
    assert {item["format"] for item in downloads} == {
        "csv",
        "html",
        "json",
        "markdown",
        "xlsx",
    }
    assert any(item["label"] == "Baixar planilha CSV" for item in downloads)
    assert any(
        item["label"] == "Baixar planilha XLSX profissional"
        for item in downloads
    )
    for item in downloads:
        assert (tmp_path / item["filename"]).exists()
        assert item["url"].startswith("/api/copilot/reports/")


def test_local_api_serves_smart_report_download(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_SMART_REPORT_OUTPUT_DIR", str(tmp_path))
    report_file = tmp_path / "business_lab_smart_report_teste.csv"
    report_file.write_text("Indicador;Valor\nLeads;10\n", encoding="utf-8")

    server = create_copilot_server(
        host="127.0.0.1",
        port=0,
        copilot_handler=lambda _payload: CopilotResponse(
            ok=True,
            answer="ok",
        ),
        api_token="",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urlopen(
            f"{base_url}/api/copilot/reports/{report_file.name}",
            timeout=2,
        ) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")

        assert "Indicador;Valor" in body
        assert "text/csv" in content_type
    finally:
        server.shutdown()
        server.server_close()


def test_professional_xlsx_download_is_valid_zip_package(tmp_path) -> None:
    report = _sample_report()
    exports = build_report_exports(report)

    files = save_report_bundle(report, exports, output_dir=tmp_path)
    xlsx_download = next(
        item for item in files["downloads"] if item["format"] == "xlsx"
    )
    xlsx_path = tmp_path / xlsx_download["filename"]

    assert xlsx_path.suffix == ".xlsx"
    assert xlsx_path.read_bytes().startswith(b"PK")
    assert xlsx_download["content_type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )


def test_report_json_download_contains_structured_payload(tmp_path) -> None:
    report = _sample_report()
    exports = build_report_exports(report)

    files = save_report_bundle(report, exports, output_dir=tmp_path)
    json_download = next(
        item for item in files["downloads"] if item["format"] == "json"
    )
    payload = json.loads((tmp_path / json_download["filename"]).read_text("utf-8"))

    assert payload["ok"] is True
    assert payload["report"]["title"] == "Relatório inteligente de teste"
    assert "csv" in payload["exports"]
