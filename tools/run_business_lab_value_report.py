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
    report_module = import_module("atlas.integrations.business_lab.value_report")
    return (
        benchmark_module.DEFAULT_OUTPUT_DIR,
        report_module.build_value_report_from_file,
        report_module.load_latest_benchmark,
        report_module.save_value_report,
    )


def main() -> int:
    default_output_dir, build_value_report_from_file, load_latest_benchmark, save_value_report = (
        _load_dependencies()
    )

    parser = argparse.ArgumentParser(
        description=(
            "Gera relatório Atlas x operação manual a partir do "
            "benchmark real do Business Lab."
        )
    )
    parser.add_argument(
        "--benchmark-json",
        type=Path,
        default=None,
        help=(
            "Caminho de um JSON business_lab_benchmark_*.json. "
            "Se omitido, usa o benchmark mais recente."
        ),
    )
    parser.add_argument(
        "--hourly-cost",
        type=float,
        default=0.0,
        help="Custo/hora em BRL para estimativa financeira opcional.",
    )
    parser.add_argument(
        "--monthly-runs",
        type=int,
        default=1,
        help="Quantidade estimada de ciclos LAB por mês.",
    )
    args = parser.parse_args()

    benchmark_path = args.benchmark_json or load_latest_benchmark(
        input_dir=default_output_dir
    )
    report = build_value_report_from_file(
        benchmark_path,
        hourly_cost_brl=args.hourly_cost,
        monthly_runs=args.monthly_runs,
    )
    json_path, csv_path, md_path = save_value_report(
        report,
        output_dir=default_output_dir,
    )

    print("Atlas x Operação Manual — Business Lab")
    print(f"Fonte benchmark: {benchmark_path}")
    print(f"Cenários: {report.passed_scenarios}/{report.total_scenarios} OK")
    print(f"Manual estimado: {report.total_manual_minutes:.2f} min")
    print(f"Atlas medido: {report.total_atlas_minutes:.2f} min")
    print(f"Economia por ciclo: {report.total_saved_minutes:.2f} min")
    print(f"Redução estimada: {report.reduction_percent:.2f}%")

    if args.hourly_cost > 0:
        print(f"Horas economizadas/mês: {report.monthly_saved_hours:.2f}h")
        print(f"Valor potencial/mês: R$ {report.monthly_estimated_value_brl:.2f}")

    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
