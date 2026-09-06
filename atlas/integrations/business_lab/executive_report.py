from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from .benchmark_runner import DEFAULT_OUTPUT_DIR

EXECUTIVE_REPORT_LABEL = "EXECUTIVE_REPORT_FROM_MEASURED_ATLAS_AND_ESTIMATED_BASELINE"


@dataclass(frozen=True, slots=True)
class ExecutiveReportFiles:
    json_path: Path
    markdown_path: Path
    html_path: Path


def load_latest_value_report(
    *,
    input_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    candidates = sorted(input_dir.glob("business_lab_value_report_*.json"))
    if not candidates:
        raise FileNotFoundError(
            "Nenhum relatório de valor encontrado. Rode primeiro "
            "tools/run_business_lab_value_report.py."
        )
    return max(candidates, key=lambda path: path.name)


def build_executive_report_from_file(
    value_report_json_path: Path,
    *,
    company_name: str = "Nexyra",
    product_name: str = "Atlas",
    client_segment: str = "operação comercial educacional",
) -> dict[str, Any]:
    payload = json.loads(value_report_json_path.read_text(encoding="utf-8"))
    return build_executive_report(
        payload,
        source_value_report_file=str(value_report_json_path),
        company_name=company_name,
        product_name=product_name,
        client_segment=client_segment,
    )


def build_executive_report(
    value_payload: dict[str, Any],
    *,
    source_value_report_file: str = "<memory>",
    company_name: str = "Nexyra",
    product_name: str = "Atlas",
    client_segment: str = "operação comercial educacional",
) -> dict[str, Any]:
    comparisons = _clean_comparisons(value_payload.get("comparisons"))
    highlights = _top_savings(comparisons, limit=3)
    success_rate = _number(value_payload.get("success_rate_percent"))
    reduction = _number(value_payload.get("reduction_percent"))
    monthly_value = _number(value_payload.get("monthly_estimated_value_brl"))

    status = "aprovado" if success_rate >= 90 else "atenção"
    headline = (
        f"{product_name} executou {success_rate:.2f}% dos cenários operacionais "
        f"do Business Lab com redução estimada de {reduction:.2f}% no ciclo."
    )

    if monthly_value > 0:
        financial_summary = (
            "Com os parâmetros informados, o potencial estimado é de "
            f"R$ {monthly_value:.2f} por mês."
        )
    else:
        financial_summary = (
            "A estimativa financeira não foi ativada porque o custo/hora foi "
            "informado como zero."
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "report_provenance": EXECUTIVE_REPORT_LABEL,
        "source_value_report_file": source_value_report_file,
        "company_name": company_name,
        "product_name": product_name,
        "client_segment": client_segment,
        "status": status,
        "headline": headline,
        "financial_summary": financial_summary,
        "metrics": {
            "total_scenarios": int(value_payload.get("total_scenarios") or 0),
            "passed_scenarios": int(value_payload.get("passed_scenarios") or 0),
            "failed_scenarios": int(value_payload.get("failed_scenarios") or 0),
            "success_rate_percent": success_rate,
            "total_manual_minutes": _number(value_payload.get("total_manual_minutes")),
            "total_atlas_minutes": _number(value_payload.get("total_atlas_minutes")),
            "total_saved_minutes": _number(value_payload.get("total_saved_minutes")),
            "reduction_percent": reduction,
            "monthly_runs": int(value_payload.get("monthly_runs") or 1),
            "hourly_cost_brl": _number(value_payload.get("hourly_cost_brl")),
            "monthly_saved_hours": _number(value_payload.get("monthly_saved_hours")),
            "monthly_estimated_value_brl": monthly_value,
        },
        "evidence": {
            "atlas_source": value_payload.get("source_provenance"),
            "manual_baseline": value_payload.get("manual_baseline_kind"),
            "value_report_source": value_payload.get("report_provenance"),
            "official_answers_used": False,
            "scenario_endpoint_used": False,
        },
        "top_savings": highlights,
        "comparisons": comparisons,
        "commercial_positioning": [
            "Automação de rotinas repetitivas em sistemas comerciais.",
            "Execução via integração de API antes de depender de navegador ou visão.",
            "Medição técnica com relatório reproduzível para demonstração.",
            "Separação clara entre resultado medido e baseline manual estimado.",
        ],
        "limitations": [
            "O Business Lab é um ambiente local e controlado, não um cliente real.",
            "A linha manual é estimada e deve ser recalibrada com pessoas reais.",
            "O relatório não substitui piloto supervisionado em produção.",
            "Ganhos financeiros são projeções baseadas nos parâmetros informados.",
        ],
        "recommended_next_steps": [
            "Rodar o mesmo benchmark com mais repetições para reduzir variação.",
            "Gravar uma demonstração curta do Atlas executando LAB-001 a LAB-010.",
            "Criar uma versão de apresentação com prints do Business Lab e do Atlas.",
            "Preparar um piloto seguro em sistema real com permissões limitadas.",
        ],
    }


def save_executive_report(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> ExecutiveReportFiles:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"business_lab_executive_report_{timestamp}.json"
    markdown_path = output_dir / f"business_lab_executive_report_{timestamp}.md"
    html_path = output_dir / f"business_lab_executive_report_{timestamp}.html"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(format_executive_markdown(report), encoding="utf-8")
    html_path.write_text(format_executive_html(report), encoding="utf-8")

    return ExecutiveReportFiles(
        json_path=json_path,
        markdown_path=markdown_path,
        html_path=html_path,
    )


def save_executive_report_from_file(
    value_report_json_path: Path,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    company_name: str = "Nexyra",
    product_name: str = "Atlas",
    client_segment: str = "operação comercial educacional",
) -> ExecutiveReportFiles:
    report = build_executive_report_from_file(
        value_report_json_path,
        company_name=company_name,
        product_name=product_name,
        client_segment=client_segment,
    )
    return save_executive_report(report, output_dir=output_dir)


def format_executive_markdown(report: dict[str, Any]) -> str:
    metrics = _dict(report.get("metrics"))
    evidence = _dict(report.get("evidence"))
    lines = [
        f"# Relatório Executivo — {report.get('product_name')} Business Lab",
        "",
        f"**Empresa:** {report.get('company_name')}",
        f"**Segmento simulado:** {report.get('client_segment')}",
        f"**Status:** {str(report.get('status')).upper()}",
        "",
        "## Resumo executivo",
        "",
        str(report.get("headline") or ""),
        "",
        str(report.get("financial_summary") or ""),
        "",
        "## Indicadores principais",
        "",
        f"- Cenários analisados: {metrics.get('total_scenarios', 0)}",
        f"- Cenários aprovados: {metrics.get('passed_scenarios', 0)}",
        f"- Taxa de sucesso: {_fmt_percent(metrics.get('success_rate_percent'))}",
        f"- Tempo manual estimado: {_fmt_minutes(metrics.get('total_manual_minutes'))}",
        f"- Tempo Atlas medido: {_fmt_minutes(metrics.get('total_atlas_minutes'))}",
        f"- Economia por ciclo: {_fmt_minutes(metrics.get('total_saved_minutes'))}",
        f"- Redução estimada: {_fmt_percent(metrics.get('reduction_percent'))}",
        f"- Horas economizadas/mês: {_fmt_hours(metrics.get('monthly_saved_hours'))}",
        f"- Potencial estimado/mês: {_fmt_money(metrics.get('monthly_estimated_value_brl'))}",
        "",
        "## Evidências e rastreabilidade",
        "",
        f"- Fonte Atlas: `{evidence.get('atlas_source')}`",
        f"- Baseline manual: `{evidence.get('manual_baseline')}`",
        f"- Relatório base: `{evidence.get('value_report_source')}`",
        "- Gabaritos oficiais usados: não",
        "- Endpoint `/api/v1/cenarios` usado: não",
        "",
        "## Maiores economias por cenário",
        "",
        "| Cenário | Descrição | Economia | Redução |",
        "|---|---|---:|---:|",
    ]

    for item in _list(report.get("top_savings")):
        lines.append(
            "| "
            f"{item.get('scenario_id')} | "
            f"{item.get('title')} | "
            f"{_fmt_seconds(item.get('saved_seconds'))} | "
            f"{_fmt_percent(item.get('reduction_percent'))} |"
        )

    lines.extend(
        [
            "",
            "## Posicionamento comercial",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _list(report.get("commercial_positioning")))
    lines.extend(
        [
            "",
            "## Limitações honestas",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _list(report.get("limitations")))
    lines.extend(
        [
            "",
            "## Próximos passos recomendados",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _list(report.get("recommended_next_steps")))
    lines.extend(
        [
            "",
            "## Declaração para demonstração",
            "",
            (
                "Este material demonstra o Atlas operando em um ambiente local "
                "controlado, com dados sintéticos e métricas reproduzíveis. "
                "Ele deve ser apresentado como evidência técnica de capacidade, "
                "não como resultado real de cliente em produção."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def format_executive_html(report: dict[str, Any]) -> str:
    metrics = _dict(report.get("metrics"))
    cards = [
        ("Sucesso", _fmt_percent(metrics.get("success_rate_percent"))),
        ("Redução", _fmt_percent(metrics.get("reduction_percent"))),
        ("Economia/ciclo", _fmt_minutes(metrics.get("total_saved_minutes"))),
        ("Potencial/mês", _fmt_money(metrics.get("monthly_estimated_value_brl"))),
    ]
    card_html = "".join(
        f"<article><span>{escape(label)}</span><strong>{escape(value)}</strong></article>"
        for label, value in cards
    )
    savings_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item.get('scenario_id')))}</td>"
        f"<td>{escape(str(item.get('title')))}</td>"
        f"<td>{escape(_fmt_seconds(item.get('saved_seconds')))}</td>"
        f"<td>{escape(_fmt_percent(item.get('reduction_percent')))}</td>"
        "</tr>"
        for item in _list(report.get("top_savings"))
    )
    limitations = "".join(
        f"<li>{escape(str(item))}</li>" for item in _list(report.get("limitations"))
    )
    next_steps = "".join(
        f"<li>{escape(str(item))}</li>"
        for item in _list(report.get("recommended_next_steps"))
    )

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Relatório Executivo — {escape(str(report.get('product_name')))}</title>
  <style>
    body {{
      margin: 0;
      background: #07111f;
      color: #eaf6ff;
      font-family: Arial, Helvetica, sans-serif;
    }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 42px 22px; }}
    .hero {{ border: 1px solid #163759; border-radius: 22px; padding: 30px; background: #0c1b2e; }}
    .eyebrow {{ color: #64d9ff; text-transform: uppercase; letter-spacing: .12em; font-size: 12px; }}
    h1 {{ margin: 12px 0; font-size: 38px; }}
    h2 {{ margin-top: 34px; color: #9eeaff; }}
    .headline {{ font-size: 20px; line-height: 1.45; color: #ffffff; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 22px 0; }}
    article {{ background: #102945; border: 1px solid #1b496f; border-radius: 18px; padding: 18px; }}
    article span {{ display: block; color: #9fb8c9; font-size: 13px; }}
    article strong {{ display: block; font-size: 26px; margin-top: 8px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ border-bottom: 1px solid #1b496f; padding: 12px; text-align: left; }}
    th {{ color: #9eeaff; }}
    .note {{ color: #b7c9d8; line-height: 1.55; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <div class="eyebrow">{escape(str(report.get('company_name')))} • Business Lab</div>
    <h1>Relatório Executivo — {escape(str(report.get('product_name')))}</h1>
    <p class="headline">{escape(str(report.get('headline')))}</p>
    <p class="note">{escape(str(report.get('financial_summary')))}</p>
  </section>

  <section class="cards">{card_html}</section>

  <h2>Maiores economias por cenário</h2>
  <table>
    <thead><tr><th>Cenário</th><th>Descrição</th><th>Economia</th><th>Redução</th></tr></thead>
    <tbody>{savings_rows}</tbody>
  </table>

  <h2>Limitações honestas</h2>
  <ul>{limitations}</ul>

  <h2>Próximos passos recomendados</h2>
  <ul>{next_steps}</ul>

  <p class="note"><strong>Declaração:</strong> Este material demonstra o Atlas em ambiente local controlado, com dados sintéticos e métricas reproduzíveis. Não deve ser apresentado como resultado real de cliente em produção.</p>
</main>
</body>
</html>
"""


def _clean_comparisons(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "scenario_id": str(row.get("scenario_id") or ""),
                "title": str(row.get("title") or ""),
                "ok": bool(row.get("ok")),
                "manual_baseline_seconds": _number(
                    row.get("manual_baseline_seconds")
                ),
                "atlas_average_seconds": _number(row.get("atlas_average_seconds")),
                "saved_seconds": _number(row.get("saved_seconds")),
                "reduction_percent": _number(row.get("reduction_percent")),
            }
        )
    return items


def _top_savings(
    comparisons: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    ranked = sorted(
        comparisons,
        key=lambda item: _number(item.get("saved_seconds")),
        reverse=True,
    )
    return ranked[:limit]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _fmt_percent(value: Any) -> str:
    return f"{_number(value):.2f}%"


def _fmt_seconds(value: Any) -> str:
    return f"{_number(value):.2f}s"


def _fmt_minutes(value: Any) -> str:
    return f"{_number(value):.2f} min"


def _fmt_hours(value: Any) -> str:
    return f"{_number(value):.2f}h"


def _fmt_money(value: Any) -> str:
    return f"R$ {_number(value):.2f}"
