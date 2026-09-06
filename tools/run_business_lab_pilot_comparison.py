from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_modules() -> tuple[Any, Any]:
    benchmark_runner = importlib.import_module(
        "atlas.integrations.business_lab.benchmark_runner"
    )
    pilot_comparison = importlib.import_module(
        "atlas.integrations.business_lab.pilot_comparison"
    )
    return benchmark_runner, pilot_comparison


def main() -> int:
    benchmark_runner, pilot_comparison = _load_modules()
    parser = argparse.ArgumentParser(
        description="Compara Atlas x operação manual medida no Business Lab."
    )
    parser.add_argument(
        "--init-template",
        action="store_true",
        help="cria o CSV-modelo para preenchimento manual",
    )
    parser.add_argument(
        "--manual-csv",
        type=Path,
        default=None,
        help="CSV preenchido com tempos manuais",
    )
    parser.add_argument(
        "--benchmark-json",
        type=Path,
        default=None,
        help="benchmark JSON específico; se omitido, usa o mais recente",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=benchmark_runner.DEFAULT_OUTPUT_DIR,
        help="pasta de saída dos relatórios",
    )
    parser.add_argument(
        "--hourly-cost",
        type=float,
        default=0.0,
        help="custo/hora para estimativa financeira",
    )
    parser.add_argument(
        "--monthly-runs",
        type=int,
        default=1,
        help="quantidade de ciclos mensais para projeção",
    )
    args = parser.parse_args()

    if args.init_template or args.manual_csv is None:
        template_path = pilot_comparison.create_manual_template(
            output_dir=args.output_dir,
        )
        print("Modelo de medição manual criado:")
        print(template_path)
        if args.manual_csv is None:
            print("\nPreencha a coluna elapsed_seconds e rode novamente com:")
            print(
                "python tools/run_business_lab_pilot_comparison.py "
                f"--manual-csv {template_path}"
            )
            return 0

    report = pilot_comparison.build_pilot_comparison_from_files(
        manual_csv_path=args.manual_csv,
        benchmark_json_path=args.benchmark_json,
        input_dir=args.output_dir,
        hourly_cost_brl=args.hourly_cost,
        monthly_runs=args.monthly_runs,
    )
    json_path, csv_path, md_path = pilot_comparison.save_pilot_comparison_report(
        report,
        output_dir=args.output_dir,
    )

    print("Relatório de comparação manual x Atlas gerado.")
    print(f"Cenários comparados: {report.total_scenarios}")
    print(f"Sucesso Atlas: {report.success_rate_percent:.2f}%")
    print(f"Redução medida: {report.reduction_percent:.2f}%")
    print(f"Economia por ciclo: {report.total_saved_minutes:.2f} min")
    if report.hourly_cost_brl > 0:
        print(f"Horas economizadas/mês: {report.monthly_saved_hours:.2f}h")
        print(f"Valor potencial/mês: R$ {report.monthly_estimated_value_brl:.2f}")
    print("\nArquivos:")
    print(json_path)
    print(csv_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
