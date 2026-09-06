from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path


def _ensure_project_root() -> None:
    project_root = Path(__file__).resolve().parents[1]
    root = str(project_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa benchmark real do Atlas contra o Business Lab."
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Quantidade de repetições dos cenários LAB-001 a LAB-010.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=None,
        help="Cenário específico, ex.: LAB-001. Pode repetir a opção.",
    )
    parser.add_argument(
        "--output",
        default="data/business_lab_benchmark",
        help="Pasta de saída dos relatórios JSON e CSV.",
    )
    return parser


def main() -> int:
    _ensure_project_root()
    args = _build_parser().parse_args()

    integrations = importlib.import_module("atlas.integrations")
    benchmark_module = importlib.import_module(
        "atlas.integrations.business_lab.benchmark_runner"
    )
    lab_module = importlib.import_module(
        "atlas.integrations.business_lab.lab_runner"
    )

    email = os.getenv("ATLAS_BUSINESS_LAB_EMAIL")
    password = os.getenv("ATLAS_BUSINESS_LAB_PASSWORD")

    if not email or not password:
        print(
            "Configure ATLAS_BUSINESS_LAB_EMAIL e "
            "ATLAS_BUSINESS_LAB_PASSWORD antes do benchmark."
        )
        return 2

    scenarios = tuple(args.scenario or lab_module.LAB_SEQUENCE)
    connector = integrations.BusinessLabConnector(
        email=email,
        password=password,
    )
    runner = benchmark_module.BusinessLabBenchmarkRunner(connector)
    summary = runner.run(
        scenarios=scenarios,
        repetitions=args.repeat,
    )
    json_path, csv_path = benchmark_module.save_benchmark_report(
        summary,
        output_dir=Path(args.output),
    )

    print("Atlas Business Lab Benchmark")
    print("Origem dos dados: MEASURED_IN_LOCAL_BUSINESS_LAB")
    print("Gabaritos oficiais expostos: NÃO")
    print("Endpoint /api/v1/cenarios usado: NÃO")
    print("-" * 72)

    for sample in summary.samples:
        status = "OK" if sample.ok else "FALHOU"
        print(
            f"{sample.scenario_id} | rep={sample.repetition} | "
            f"{status} | {sample.elapsed_ms:.2f} ms | "
            f"driver={sample.driver or 'nenhum'}"
        )

    print("-" * 72)
    print(
        f"Resumo: {summary.passed}/{summary.total} execuções passaram "
        f"({summary.success_rate_percent:.2f}%)."
    )
    print(f"Tempo médio: {summary.average_elapsed_ms:.2f} ms")
    print(f"Tempo mediano: {summary.median_elapsed_ms:.2f} ms")
    print(f"Relatório JSON: {json_path}")
    print(f"Relatório CSV: {csv_path}")

    return 0 if summary.ok else 1


if __name__ == "__main__":
    sys.exit(main())
