from __future__ import annotations

import csv
import io
import json
import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from typing import Any, Protocol

from atlas.integrations.base import IntegrationResult

from .models import (
    CopilotActionResult,
    CopilotRequest,
    CopilotResponse,
)

DEFAULT_REPORT_LIMIT = 50
MAX_REPORT_LIMIT = 500
DEFAULT_SMART_REPORT_DIR = Path("data") / "business_lab_benchmark"
SMART_REPORT_FILE_PREFIX = "business_lab_smart_report"


class SmartReportExecutor(Protocol):
    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult: ...


@dataclass(frozen=True, slots=True)
class SmartReportFilters:
    focus: str = "geral"
    requested_limit: int = DEFAULT_REPORT_LIMIT
    course_id: int | None = None
    course_name: str = ""
    lead_status: str = ""
    priority: str = ""
    enrollment_status: str = ""
    payment_status: str = ""
    followup_status: str = ""
    followup_due_filter: str = ""
    period_label: str = "base completa"

    def report_kwargs(self) -> dict[str, Any]:
        return {"course_id": self.course_id}

    def leads_kwargs(self) -> dict[str, Any]:
        return {
            "course_id": self.course_id,
            "status": self.lead_status,
            "priority": self.priority,
            "limit": self.requested_limit,
        }

    def enrollments_kwargs(self) -> dict[str, Any]:
        return {
            "course_id": self.course_id,
            "status": self.enrollment_status,
            "payment_status": self.payment_status,
            "limit": self.requested_limit,
        }

    def followups_kwargs(self) -> dict[str, Any]:
        return {
            "status": self.followup_status,
            "priority": self.priority,
            "due_filter": self.followup_due_filter,
            "limit": self.requested_limit,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "focus": self.focus,
            "requested_limit": self.requested_limit,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "lead_status": self.lead_status,
            "priority": self.priority,
            "enrollment_status": self.enrollment_status,
            "payment_status": self.payment_status,
            "followup_status": self.followup_status,
            "followup_due_filter": self.followup_due_filter,
            "period_label": self.period_label,
        }


@dataclass(frozen=True, slots=True)
class SmartReportResult:
    title: str
    generated_at: str
    filters: SmartReportFilters
    metrics: dict[str, Any]
    tables: dict[str, list[dict[str, Any]]]
    insights: list[str]
    alerts: list[str]
    next_steps: list[str]
    source_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "filters": self.filters.to_dict(),
            "metrics": self.metrics,
            "tables": self.tables,
            "insights": self.insights,
            "alerts": self.alerts,
            "next_steps": self.next_steps,
            "source_notes": self.source_notes,
        }


def looks_like_smart_report_command(message: str) -> bool:
    text = _normalize(message)
    report_markers = (
        "relatorio",
        "relatorios",
        "analise",
        "analisar",
        "indicadores",
        "produtividade",
        "conversao",
        "gargalo",
        "gargalos",
        "oportunidade",
        "oportunidades",
        "resumo executivo",
        "gere",
        "gerar",
        "liste",
        "listar",
        "mostre",
        "mostrar",
    )
    subject_markers = (
        "lead",
        "leads",
        "matricula",
        "matriculas",
        "retorno",
        "retornos",
        "atendimento",
        "atendimentos",
        "curso",
        "cursos",
        "consultor",
        "consultores",
        "operacao",
        "comercial",
    )
    return any(marker in text for marker in report_markers) and any(
        marker in text for marker in subject_markers
    )


def run_smart_report(
    request: CopilotRequest,
    manager: SmartReportExecutor,
) -> CopilotResponse:
    courses_result = manager.execute("business_lab", "list_courses")
    courses = _safe_list(courses_result.data) if courses_result.ok else []
    filters = _build_filters(request.message, courses)

    report_result = manager.execute(
        "business_lab",
        "get_reports",
        **filters.report_kwargs(),
    )
    leads_result = manager.execute(
        "business_lab",
        "list_leads",
        **filters.leads_kwargs(),
    )
    enrollments_result = manager.execute(
        "business_lab",
        "list_enrollments",
        **filters.enrollments_kwargs(),
    )
    followups_result = manager.execute(
        "business_lab",
        "list_all_followups",
        **filters.followups_kwargs(),
    )
    interactions_result = manager.execute(
        "business_lab",
        "list_recent_interactions",
        limit=filters.requested_limit,
    )
    dashboard_result = manager.execute("business_lab", "dashboard")

    actions = (
        _action_result(courses_result),
        _action_result(report_result),
        _action_result(leads_result),
        _action_result(enrollments_result),
        _action_result(followups_result),
        _action_result(interactions_result),
        _action_result(dashboard_result),
    )

    if not report_result.ok:
        return CopilotResponse(
            ok=False,
            intent="smart_reports",
            context=request.context,
            answer=report_result.error or "Não consegui gerar o relatório.",
            actions=actions,
            error=report_result.error or "Falha ao consultar relatório do Lab.",
        )

    report = build_smart_report_payload(
        filters=filters,
        report_data=_as_dict(report_result.data),
        leads=_safe_list(leads_result.data) if leads_result.ok else [],
        enrollments=(
            _safe_list(enrollments_result.data) if enrollments_result.ok else []
        ),
        followups=_safe_list(followups_result.data) if followups_result.ok else [],
        interactions=(
            _safe_list(interactions_result.data) if interactions_result.ok else []
        ),
    )
    exports = build_report_exports(report)
    files = save_report_bundle(report, exports)

    return CopilotResponse(
        ok=True,
        intent="smart_reports",
        context=request.context,
        answer=_format_answer(report),
        actions=actions,
        data={
            "report": report.to_dict(),
            "exports": exports,
            "files": files,
            "mode": "smart_business_lab_report",
            "source": "Business Lab API via Atlas Integration Framework",
        },
        requires_human_review=False,
    )


def build_smart_report_payload(
    *,
    filters: SmartReportFilters,
    report_data: dict[str, Any],
    leads: list[Any],
    enrollments: list[Any],
    followups: list[Any],
    interactions: list[Any],
) -> SmartReportResult:
    lead_rows = [lead for lead in leads if isinstance(lead, dict)]
    enrollment_rows = [item for item in enrollments if isinstance(item, dict)]
    followup_rows = [item for item in followups if isinstance(item, dict)]
    interaction_rows = [item for item in interactions if isinstance(item, dict)]

    metrics = _build_metrics(
        report_data=report_data,
        leads=lead_rows,
        enrollments=enrollment_rows,
        followups=followup_rows,
        interactions=interaction_rows,
    )
    tables = _build_tables(
        report_data=report_data,
        leads=lead_rows,
        enrollments=enrollment_rows,
        followups=followup_rows,
        interactions=interaction_rows,
    )
    insights = _build_insights(metrics, tables, filters)
    alerts = _build_alerts(metrics, tables)
    next_steps = _build_next_steps(metrics, alerts, filters)
    title = _build_title(filters)

    return SmartReportResult(
        title=title,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        filters=filters,
        metrics=metrics,
        tables=tables,
        insights=insights,
        alerts=alerts,
        next_steps=next_steps,
        source_notes=[
            "Dados lidos pela API do Nexyra Business Lab.",
            "Não acessa banco diretamente e não usa gabaritos oficiais LAB.",
            "Períodos textuais são preservados como contexto; a API atual "
            "consolida os dados operacionais disponíveis.",
        ],
    )


def build_report_exports(report: SmartReportResult) -> dict[str, str]:
    return {
        "markdown": report_to_markdown(report),
        "csv": report_to_csv(report),
        "html": report_to_html(report),
    }


def save_report_bundle(
    report: SmartReportResult,
    exports: dict[str, str],
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Salva o relatório inteligente e prepara links locais de download.

    Os arquivos ficam no Atlas, mas o Business Lab pode baixá-los pelo
    endpoint local do Copilot Bridge: /api/copilot/reports/<arquivo>.
    """
    target_dir = _report_output_dir(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{SMART_REPORT_FILE_PREFIX}_{_safe_timestamp(report.generated_at)}"
    payload = {
        "ok": True,
        "report": report.to_dict(),
        "exports": exports,
        "source": "ATLAS_SMART_REPORTS_LOCAL",
    }

    files: list[dict[str, str]] = []
    _write_report_file(
        files,
        target_dir / f"{base_name}.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
        label="Baixar JSON",
        format_name="json",
        content_type="application/json",
    )
    _write_report_binary_file(
        files,
        target_dir / f"{base_name}.xlsx",
        report_to_xlsx_bytes(report),
        label="Baixar planilha XLSX profissional",
        format_name="xlsx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    _write_report_file(
        files,
        target_dir / f"{base_name}.csv",
        exports.get("csv", ""),
        label="Baixar planilha CSV",
        format_name="csv",
        content_type="text/csv",
    )
    _write_report_file(
        files,
        target_dir / f"{base_name}.md",
        exports.get("markdown", ""),
        label="Baixar Markdown",
        format_name="markdown",
        content_type="text/markdown",
    )
    _write_report_file(
        files,
        target_dir / f"{base_name}.html",
        exports.get("html", ""),
        label="Baixar HTML",
        format_name="html",
        content_type="text/html",
    )

    return {
        "directory": str(target_dir),
        "base_filename": base_name,
        "downloads": files,
    }


def _report_output_dir(output_dir: Path | None = None) -> Path:
    configured = os.getenv("ATLAS_SMART_REPORT_OUTPUT_DIR")
    if output_dir is not None:
        return output_dir
    if configured:
        return Path(configured)
    return DEFAULT_SMART_REPORT_DIR


def _safe_timestamp(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "_", value.strip())
    return cleaned.strip("_") or datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_report_file(
    files: list[dict[str, str]],
    path: Path,
    content: str,
    *,
    label: str,
    format_name: str,
    content_type: str,
) -> None:
    if not content:
        return
    path.write_text(content, encoding="utf-8")
    files.append(
        {
            "format": format_name,
            "label": label,
            "filename": path.name,
            "url": f"/api/copilot/reports/{path.name}",
            "content_type": content_type,
        }
    )


def _write_report_binary_file(
    files: list[dict[str, str]],
    path: Path,
    content: bytes,
    *,
    label: str,
    format_name: str,
    content_type: str,
) -> None:
    if not content:
        return
    path.write_bytes(content)
    files.append(
        {
            "format": format_name,
            "label": label,
            "filename": path.name,
            "url": f"/api/copilot/reports/{path.name}",
            "content_type": content_type,
        }
    )


def report_to_markdown(report: SmartReportResult) -> str:
    lines = [
        f"# {report.title}",
        "",
        f"Gerado em: {report.generated_at}",
        f"Período solicitado: {report.filters.period_label}",
        "",
        "## Indicadores principais",
    ]
    for key, value in report.metrics.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Insights"])
    for insight in report.insights:
        lines.append(f"- {insight}")

    lines.extend(["", "## Alertas"])
    for alert in report.alerts or ["Nenhum alerta crítico detectado."]:
        lines.append(f"- {alert}")

    lines.extend(["", "## Próximos passos"])
    for step in report.next_steps:
        lines.append(f"- {step}")

    lines.extend(["", "## Observações de origem"])
    for note in report.source_notes:
        lines.append(f"- {note}")

    return "\n".join(lines) + "\n"


def report_to_csv(report: SmartReportResult) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(["NEXYRA BUSINESS LAB - RELATÓRIO INTELIGENTE ATLAS"])
    writer.writerow(["Título", report.title])
    writer.writerow(["Gerado em", report.generated_at])
    writer.writerow(["Período solicitado", report.filters.period_label])
    writer.writerow([])
    writer.writerow(["Indicador", "Valor"])
    for key, value in report.metrics.items():
        writer.writerow([key, value])
    writer.writerow([])
    writer.writerow(["Insight"])
    for insight in report.insights:
        writer.writerow([insight])
    writer.writerow([])
    writer.writerow(["Alerta"])
    for alert in report.alerts:
        writer.writerow([alert])
    writer.writerow([])
    writer.writerow(["Próximo passo"])
    for step in report.next_steps:
        writer.writerow([step])
    return buffer.getvalue()


def report_to_xlsx_bytes(report: SmartReportResult) -> bytes:
    """Gera uma planilha XLSX profissional sem dependências externas."""
    rows: list[dict[str, Any]] = []
    merges: list[str] = []

    def add(values: list[Any], style: int = 0, height: float | None = None) -> int:
        rows.append({"values": values, "style": style, "height": height})
        return len(rows)

    title_row = add(["NEXYRA BUSINESS LAB", "RELATÓRIO INTELIGENTE ATLAS"], 1, 28)
    merges.append(f"A{title_row}:F{title_row}")
    subtitle_row = add([report.title], 2, 22)
    merges.append(f"A{subtitle_row}:F{subtitle_row}")
    add(["Gerado em", report.generated_at, "Período", report.filters.period_label], 3)
    add([])

    add(["Indicador", "Valor", "", "Resumo executivo", "", ""], 4, 20)
    metric_start = len(rows) + 1
    for key, value in report.metrics.items():
        add([_humanize_key(key), value, "", "", "", ""], 5)

    insight_start = metric_start
    for offset, insight in enumerate(report.insights[:8]):
        row_index = insight_start + offset
        if row_index <= len(rows):
            rows[row_index - 1]["values"][3] = "Insight" if offset == 0 else ""
            rows[row_index - 1]["values"][4] = insight
            if offset == 0:
                rows[row_index - 1]["style"] = 6
        else:
            add(["", "", "", "", insight, ""], 6)

    add([])
    add(["Alertas operacionais"], 7, 20)
    for alert in report.alerts or ["Nenhum alerta crítico detectado."]:
        add([alert], 8, 24)
    add([])
    add(["Próximos passos recomendados"], 7, 20)
    for step in report.next_steps:
        add([step], 9, 24)

    _append_table(rows, "Funil comercial", report.tables.get("funil", []), 11)
    _append_table(rows, "Leads analisados", report.tables.get("leads", []), 11)
    _append_table(rows, "Matrículas", report.tables.get("matriculas", []), 11)
    _append_table(rows, "Retornos", report.tables.get("retornos", []), 11)
    _append_table(rows, "Atendimentos", report.tables.get("atendimentos", []), 11)

    sheet_xml = _build_sheet_xml(rows, merges)
    return _build_xlsx_package(sheet_xml)


def _append_table(
    rows: list[dict[str, Any]],
    title: str,
    table_rows: list[dict[str, Any]],
    max_rows: int,
) -> None:
    if not table_rows:
        return
    rows.append({"values": [], "style": 0, "height": None})
    rows.append({"values": [title], "style": 7, "height": 20})
    headers = _table_headers(table_rows)
    rows.append(
        {
            "values": [_humanize_key(header) for header in headers],
            "style": 10,
            "height": 18,
        }
    )
    for item in table_rows[:max_rows]:
        rows.append(
            {
                "values": [item.get(header, "") for header in headers],
                "style": 11,
                "height": 20,
            }
        )


def _table_headers(table_rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "synthetic_code",
        "enrollment_code",
        "name",
        "lead_name",
        "student_name",
        "course_name",
        "status",
        "priority",
        "payment_status",
        "source",
        "channel",
        "outcome",
        "is_overdue",
        "total",
        "converted",
        "conversion_rate",
    ]
    available: list[str] = []
    for key in preferred:
        if any(key in row for row in table_rows):
            available.append(key)
    for row in table_rows:
        for key in row:
            if key not in available and len(available) < 8:
                available.append(key)
    return available[:8]


def _humanize_key(key: str) -> str:
    labels = {
        "total_leads_reportado": "Total de leads reportado",
        "leads_filtrados_na_amostra": "Leads filtrados na amostra",
        "leads_prioridade_alta_na_amostra": "Leads de prioridade alta",
        "taxa_conversao_reportada": "Taxa de conversão reportada (%)",
        "matriculas_reportadas": "Matrículas reportadas",
        "matriculas_filtradas_na_amostra": "Matrículas na amostra",
        "matriculas_ativas_na_amostra": "Matrículas ativas",
        "pagamentos_confirmados_na_amostra": "Pagamentos confirmados",
        "atendimentos_recentes_na_amostra": "Atendimentos recentes",
        "retornos_filtrados_na_amostra": "Retornos filtrados",
        "retornos_pendentes_na_amostra": "Retornos pendentes",
        "retornos_atrasados_na_amostra": "Retornos atrasados",
        "projecao_mensal_reportada": "Projeção mensal reportada",
        "synthetic_code": "Código do lead",
        "enrollment_code": "Código da matrícula",
        "name": "Nome",
        "lead_name": "Lead",
        "student_name": "Aluno",
        "course_name": "Curso",
        "status": "Status",
        "priority": "Prioridade",
        "payment_status": "Pagamento",
        "source": "Origem",
        "channel": "Canal",
        "outcome": "Resultado",
        "is_overdue": "Atrasado",
        "total": "Total",
        "converted": "Convertidos",
        "conversion_rate": "Conversão (%)",
    }
    return labels.get(key, key.replace("_", " ").capitalize())


def _build_sheet_xml(rows: list[dict[str, Any]], merges: list[str]) -> str:
    col_widths = [28, 18, 4, 20, 64, 18, 18, 18]
    cols = "".join(
        f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>'
        for idx, width in enumerate(col_widths, start=1)
    )
    row_xml = []
    for row_idx, row in enumerate(rows, start=1):
        height = row.get("height")
        height_attr = f' ht="{height}" customHeight="1"' if height else ""
        cells = []
        values = list(row.get("values", []))
        style = int(row.get("style", 0) or 0)
        for col_idx, value in enumerate(values, start=1):
            ref = f"{_column_name(col_idx)}{row_idx}"
            cells.append(_cell_xml(ref, value, style))
        row_xml.append(f'<row r="{row_idx}"{height_attr}>{"".join(cells)}</row>')

    merge_xml = ""
    if merges:
        refs = "".join(f'<mergeCell ref="{merge}"/>' for merge in merges)
        merge_xml = f'<mergeCells count="{len(merges)}">{refs}</mergeCells>'

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        f'<cols>{cols}</cols>'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        f'{merge_xml}'
        '</worksheet>'
    )


def _cell_xml(ref: str, value: Any, style: int) -> str:
    style_attr = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        numeric = "1" if value else "0"
        return f'<c r="{ref}"{style_attr}><v>{numeric}</v></c>'
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = xml_escape(str(value))
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>'


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _build_xlsx_package(sheet_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _xlsx_content_types())
        package.writestr("_rels/.rels", _xlsx_root_relationships())
        package.writestr("xl/workbook.xml", _xlsx_workbook())
        package.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_relationships())
        package.writestr("xl/styles.xml", _xlsx_styles())
        package.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def _xlsx_content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""


def _xlsx_root_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _xlsx_workbook() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Relatório Atlas" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""


def _xlsx_workbook_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _xlsx_styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="5">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="16"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <font><b/><sz val="12"/><color rgb="FF8EE8FF"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <font><sz val="10"/><color rgb="FF0F172A"/><name val="Calibri"/></font>
  </fonts>
  <fills count="8">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF071827"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF0B2A3D"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF0EA5E9"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE0F2FE"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF7ED"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFECFDF5"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left style="thin"><color rgb="FFCBD5E1"/></left><right style="thin"><color rgb="FFCBD5E1"/></right><top style="thin"><color rgb="FFCBD5E1"/></top><bottom style="thin"><color rgb="FFCBD5E1"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="12">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="4" fillId="6" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def report_to_html(report: SmartReportResult) -> str:
    metrics = "".join(
        f"<li><strong>{escape(str(key))}:</strong> {escape(str(value))}</li>"
        for key, value in report.metrics.items()
    )
    insights = "".join(f"<li>{escape(item)}</li>" for item in report.insights)
    alerts = "".join(
        f"<li>{escape(item)}</li>"
        for item in report.alerts or ["Nenhum alerta crítico detectado."]
    )
    steps = "".join(f"<li>{escape(item)}</li>" for item in report.next_steps)
    return f"""<!doctype html>
<html lang=\"pt-BR\">
<head>
  <meta charset=\"utf-8\">
  <title>{escape(report.title)}</title>
</head>
<body>
  <h1>{escape(report.title)}</h1>
  <p><strong>Gerado em:</strong> {escape(report.generated_at)}</p>
  <p><strong>Período solicitado:</strong> {escape(report.filters.period_label)}</p>
  <h2>Indicadores principais</h2>
  <ul>{metrics}</ul>
  <h2>Insights</h2>
  <ul>{insights}</ul>
  <h2>Alertas</h2>
  <ul>{alerts}</ul>
  <h2>Próximos passos</h2>
  <ul>{steps}</ul>
</body>
</html>
"""


def _build_metrics(
    *,
    report_data: dict[str, Any],
    leads: list[dict[str, Any]],
    enrollments: list[dict[str, Any]],
    followups: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
) -> dict[str, Any]:
    high_priority = sum(1 for lead in leads if lead.get("priority") == "alta")
    overdue_followups = sum(1 for item in followups if item.get("is_overdue"))
    pending_followups = sum(1 for item in followups if item.get("status") == "pendente")
    confirmed_payments = sum(
        1 for item in enrollments if item.get("payment_status") == "confirmado"
    )
    active_enrollments = sum(
        1 for item in enrollments if item.get("status") == "ativa"
    )

    return {
        "total_leads_reportado": report_data.get("total_leads", len(leads)),
        "leads_filtrados_na_amostra": len(leads),
        "leads_prioridade_alta_na_amostra": high_priority,
        "taxa_conversao_reportada": report_data.get("conversion_rate", 0),
        "matriculas_reportadas": report_data.get(
            "total_enrollments",
            len(enrollments),
        ),
        "matriculas_filtradas_na_amostra": len(enrollments),
        "matriculas_ativas_na_amostra": active_enrollments,
        "pagamentos_confirmados_na_amostra": confirmed_payments,
        "atendimentos_recentes_na_amostra": len(interactions),
        "retornos_filtrados_na_amostra": len(followups),
        "retornos_pendentes_na_amostra": pending_followups,
        "retornos_atrasados_na_amostra": overdue_followups,
        "projecao_mensal_reportada": report_data.get("monthly_projection", 0),
    }


def _build_tables(
    *,
    report_data: dict[str, Any],
    leads: list[dict[str, Any]],
    enrollments: list[dict[str, Any]],
    followups: list[dict[str, Any]],
    interactions: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "funil": _safe_table(report_data.get("funnel")),
        "origens": _safe_table(report_data.get("sources")),
        "cursos": _safe_table(report_data.get("courses")),
        "leads": leads[:20],
        "matriculas": enrollments[:20],
        "retornos": followups[:20],
        "atendimentos": interactions[:20],
    }


def _build_insights(
    metrics: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
    filters: SmartReportFilters,
) -> list[str]:
    insights: list[str] = []
    conversion = float(metrics.get("taxa_conversao_reportada") or 0)
    high_priority = int(metrics.get("leads_prioridade_alta_na_amostra") or 0)
    overdue = int(metrics.get("retornos_atrasados_na_amostra") or 0)
    enrollments = int(metrics.get("matriculas_reportadas") or 0)

    if filters.course_name:
        insights.append(f"O relatório está focado no curso {filters.course_name}.")
    if conversion > 0:
        insights.append(f"A conversão reportada está em {conversion:.2f}%.")
    if high_priority:
        insights.append(
            f"Existem {high_priority} leads de prioridade alta na amostra filtrada."
        )
    if overdue:
        insights.append(f"Há {overdue} retornos atrasados exigindo ação rápida.")
    if enrollments:
        insights.append(f"A operação possui {enrollments} matrículas reportadas.")

    top_course = _top_by(tables.get("cursos", []), "leads")
    if top_course:
        insights.append(
            "Curso com maior volume de leads: "
            f"{top_course.get('name')} ({top_course.get('leads')} leads)."
        )

    if not insights:
        insights.append(
            "O Atlas consolidou os dados disponíveis e não encontrou anomalia crítica."
        )
    return insights


def _build_alerts(
    metrics: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
) -> list[str]:
    alerts: list[str] = []
    conversion = float(metrics.get("taxa_conversao_reportada") or 0)
    overdue = int(metrics.get("retornos_atrasados_na_amostra") or 0)
    pending = int(metrics.get("retornos_pendentes_na_amostra") or 0)
    high_priority = int(metrics.get("leads_prioridade_alta_na_amostra") or 0)

    if conversion < 15:
        alerts.append(
            "Conversão abaixo de 15%: revisar abordagem, oferta e "
            "velocidade de retorno."
        )
    if overdue:
        alerts.append(
            f"Existem {overdue} retornos atrasados; priorize esses contatos."
        )
    if pending >= 20:
        alerts.append(
            f"Fila com {pending} retornos pendentes; risco de perda por demora."
        )
    if high_priority >= 5:
        alerts.append(
            f"Há {high_priority} leads quentes na amostra; tratar antes dos frios."
        )

    weak_sources = [
        source
        for source in tables.get("origens", [])
        if float(source.get("conversion_rate") or 0) < 10
        and int(source.get("total") or 0) >= 5
    ]
    for source in weak_sources[:3]:
        alerts.append(
            f"Origem {source.get('source')} com conversão baixa: "
            f"{source.get('conversion_rate')}%."
        )
    return alerts


def _build_next_steps(
    metrics: dict[str, Any],
    alerts: list[str],
    filters: SmartReportFilters,
) -> list[str]:
    steps: list[str] = []
    if int(metrics.get("retornos_atrasados_na_amostra") or 0):
        steps.append("Executar lote de retornos atrasados com prioridade alta.")
    if int(metrics.get("leads_prioridade_alta_na_amostra") or 0):
        steps.append("Fazer triagem dos leads quentes e criar plano de contato diário.")
    if filters.focus in {"matriculas", "geral"}:
        steps.append("Conferir matrículas com pagamento pendente e cobrar confirmação.")
    if filters.focus in {"atendimentos", "geral"}:
        steps.append(
            "Revisar atendimentos sem resposta e ajustar mensagem de abordagem."
        )
    if alerts:
        steps.append("Acompanhar alertas no próximo relatório para validar melhora.")
    if not steps:
        steps.append(
            "Manter monitoramento e gerar novo relatório ao final do expediente."
        )
    return steps


def _format_answer(report: SmartReportResult) -> str:
    metrics = report.metrics
    alerts = len(report.alerts)
    return (
        f"Relatório inteligente gerado: {report.title}. "
        f"Leads reportados: {metrics.get('total_leads_reportado')}; "
        f"matrículas: {metrics.get('matriculas_reportadas')}; "
        f"atendimentos recentes na amostra: "
        f"{metrics.get('atendimentos_recentes_na_amostra')}; "
        f"retornos pendentes na amostra: "
        f"{metrics.get('retornos_pendentes_na_amostra')}. "
        f"Alertas encontrados: {alerts}. "
        "Incluí resumo executivo, insights, próximos passos e exportações."
    )


def _build_filters(message: str, courses: list[Any]) -> SmartReportFilters:
    text = _normalize(message)
    course_id, course_name = _extract_course(text, courses)
    requested_limit = _extract_limit(text)
    return SmartReportFilters(
        focus=_extract_focus(text),
        requested_limit=requested_limit,
        course_id=course_id,
        course_name=course_name,
        lead_status=_extract_lead_status(text),
        priority=_extract_priority(text),
        enrollment_status=_extract_enrollment_status(text),
        payment_status=_extract_payment_status(text),
        followup_status=_extract_followup_status(text),
        followup_due_filter=_extract_followup_due_filter(text),
        period_label=_extract_period_label(text),
    )


def _extract_focus(text: str) -> str:
    if "matricula" in text:
        return "matriculas"
    if "retorno" in text:
        return "retornos"
    if "atendimento" in text:
        return "atendimentos"
    if "lead" in text:
        return "leads"
    return "geral"


def _extract_limit(text: str) -> int:
    match = re.search(r"\b(\d{1,3})\b", text)
    if match is None:
        return DEFAULT_REPORT_LIMIT
    return max(1, min(int(match.group(1)), MAX_REPORT_LIMIT))


def _extract_course(text: str, courses: list[Any]) -> tuple[int | None, str]:
    for course in courses:
        if not isinstance(course, dict):
            continue
        name = str(course.get("name") or "")
        normalized = _normalize(name)
        if normalized and normalized in text:
            return int(course.get("id") or 0), name
    return None, ""


def _extract_lead_status(text: str) -> str:
    if "em atendimento" in text or "em_atendimento" in text:
        return "em_atendimento"
    if "follow up" in text or "follow-up" in text or "follow_up" in text:
        return "follow_up"
    if "convertido" in text or "convertidos" in text:
        return "convertido"
    if "perdido" in text or "perdidos" in text:
        return "perdido"
    if "novo" in text or "novos" in text:
        return "novo"
    return ""


def _extract_priority(text: str) -> str:
    if "prioridade alta" in text or "alta prioridade" in text:
        return "alta"
    if "prioridade media" in text or "prioridade média" in text:
        return "media"
    if "prioridade baixa" in text or "baixa prioridade" in text:
        return "baixa"
    return ""


def _extract_enrollment_status(text: str) -> str:
    if "pre matricula" in text or "pre-matricula" in text:
        return "pre_matricula"
    if "ativa" in text or "ativas" in text:
        return "ativa"
    if "cancelada" in text or "canceladas" in text:
        return "cancelada"
    if "concluida" in text or "concluidas" in text:
        return "concluida"
    return ""


def _extract_payment_status(text: str) -> str:
    if "pagamento confirmado" in text or "pagamentos confirmados" in text:
        return "confirmado"
    if "pagamento pendente" in text or "pagamentos pendentes" in text:
        return "pendente"
    if "isento" in text or "isentos" in text:
        return "isento"
    return ""


def _extract_followup_status(text: str) -> str:
    if "pendente" in text or "pendentes" in text:
        return "pendente"
    if "concluido" in text or "concluidos" in text:
        return "concluido"
    if "cancelado" in text or "cancelados" in text:
        return "cancelado"
    return ""


def _extract_followup_due_filter(text: str) -> str:
    if "atrasado" in text or "atrasados" in text:
        return "atrasado"
    if "hoje" in text:
        return "hoje"
    if "proximo" in text or "proximos" in text or "amanha" in text:
        return "proximos"
    return ""


def _extract_period_label(text: str) -> str:
    if "hoje" in text:
        return "hoje"
    if "semana" in text:
        return "esta semana"
    if "mes" in text:
        return "este mês"
    if "ano" in text:
        return "este ano"
    return "base completa"


def _build_title(filters: SmartReportFilters) -> str:
    base = "Relatório inteligente do Business Lab"
    if filters.focus != "geral":
        base = f"Relatório inteligente de {filters.focus}"
    if filters.course_name:
        return f"{base} — {filters.course_name}"
    return base


def _top_by(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    if not rows:
        return {}
    return max(rows, key=lambda row: int(row.get(key) or 0))


def _safe_table(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _action_result(result: IntegrationResult) -> CopilotActionResult:
    return CopilotActionResult(
        action=result.action,
        ok=result.ok,
        driver=result.driver.value if result.driver else None,
        error=result.error,
        data=result.data,
    )


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode(
        "ascii",
        "ignore",
    ).decode("ascii")
    return " ".join(text.lower().split())
