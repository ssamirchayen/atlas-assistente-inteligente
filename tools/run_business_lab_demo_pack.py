from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dependencies() -> tuple[Any, Any]:
    benchmark_module = import_module("atlas.integrations.business_lab.benchmark_runner")
    demo_module = import_module("atlas.integrations.business_lab.demo_pack")
    return benchmark_module.DEFAULT_OUTPUT_DIR, demo_module.create_demo_pack


def main() -> int:
    default_output_dir, create_demo_pack = _load_dependencies()

    parser = argparse.ArgumentParser(
        description=(
            "Gera um pacote comercial de demonstração com os relatórios "
            "Business Lab mais recentes."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_output_dir,
        help="Pasta onde estão os relatórios gerados nas etapas 14.1 a 14.3.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Pasta onde o pacote de demonstração será salvo.",
    )
    parser.add_argument(
        "--company-name",
        default="Nexyra",
        help="Nome da empresa apresentado no pacote.",
    )
    parser.add_argument(
        "--product-name",
        default="Atlas",
        help="Nome do produto apresentado no pacote.",
    )
    parser.add_argument(
        "--client-segment",
        default="operação comercial educacional",
        help="Segmento ou cenário comercial usado na demonstração.",
    )
    args = parser.parse_args()

    result = create_demo_pack(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        company_name=args.company_name,
        product_name=args.product_name,
        client_segment=args.client_segment,
    )

    print("Demo Pack Comercial — Atlas Business Lab")
    print(f"Pasta: {result.folder_path}")
    print(f"ZIP:   {result.zip_path}")
    print(f"Manifesto: {result.manifest_path}")
    print("Arquivos incluídos:")
    for path in result.included_files:
        print(f"- {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
