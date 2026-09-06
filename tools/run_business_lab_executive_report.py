from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dependencies() -> tuple[Any, Any, Any, Any]:
    benchmark_module = import_module("atlas.integrations.business_lab.benchmark_runner")
    executive_module = import_module("atlas.integrations.business_lab.executive_report")
    return (
        benchmark_module.DEFAULT_OUTPUT_DIR,
        executive_module.build_executive_report_from_file,
        executive_module.load_latest_value_report,
        executive_module.save_executive_report,
    )


def main() -> int:
    (
        default_output_dir,
        build_executive_report_from_file,
        load_latest_value_report,
        save_executive_report,
    ) = _load_dependencies()

    parser = argparse.ArgumentParser(
        description=(
            "Gera relatório executivo comercial do Atlas a partir do relatório "
            "Atlas x operação manual do Business Lab."
        )
    )
    parser.add_argument(
        "--value-report-json",
        type=Path,
        default=None,
        help=(
            "Caminho de um JSON business_lab_value_report_*.json. "
            "Se omitido, usa o relatório de valor mais recente."
        ),
    )
    parser.add_argument(
        "--company-name",
        default="Nexyra",
        help="Nome da empresa apresentado no relatório.",
    )
    parser.add_argument(
        "--product-name",
        default="Atlas",
        help="Nome do produto apresentado no relatório.",
    )
    parser.add_argument(
        "--client-segment",
        default="operação comercial educacional",
        help="Segmento ou cenário de negócio usado na apresentação.",
    )
    args = parser.parse_args()

    value_report_path = args.value_report_json or load_latest_value_report(
        input_dir=default_output_dir
    )
    report = build_executive_report_from_file(
        value_report_path,
        company_name=args.company_name,
        product_name=args.product_name,
        client_segment=args.client_segment,
    )
    files = save_executive_report(report, output_dir=default_output_dir)

    metrics = report["metrics"]
    print("Relatório Executivo Comercial — Atlas Business Lab")
    print(f"Fonte relatório de valor: {value_report_path}")
    print(f"Empresa: {report['company_name']}")
    print(f"Produto: {report['product_name']}")
    print(f"Status: {report['status'].upper()}")
    print(f"Sucesso operacional: {metrics['success_rate_percent']:.2f}%")
    print(f"Redução estimada: {metrics['reduction_percent']:.2f}%")
    print(f"Economia por ciclo: {metrics['total_saved_minutes']:.2f} min")
    print(f"Potencial/mês: R$ {metrics['monthly_estimated_value_brl']:.2f}")
    print(f"JSON: {files.json_path}")
    print(f"MD:   {files.markdown_path}")
    print(f"HTML: {files.html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
