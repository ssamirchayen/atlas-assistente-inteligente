from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_visual_validation_module() -> Any:
    return importlib.import_module("atlas.copilot.visual_validation")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validação final visual do Atlas Copilot no Business Lab.",
    )
    parser.add_argument(
        "--business-lab-url",
        default=os.getenv("ATLAS_BUSINESS_LAB_URL", "http://127.0.0.1:5055"),
        help="URL local do Nexyra Business Lab.",
    )
    parser.add_argument(
        "--atlas-bridge-url",
        default=os.getenv("ATLAS_COPILOT_BRIDGE_URL", "http://127.0.0.1:8765"),
        help="URL local do Atlas Copilot Bridge.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("ATLAS_COPILOT_TOKEN", ""),
        help="Token local opcional do Atlas Copilot Bridge.",
    )
    parser.add_argument(
        "--lead-code",
        default="SIM-00001",
        help="Lead usado como contexto da validação.",
    )
    parser.add_argument(
        "--user-email",
        default=os.getenv("ATLAS_BUSINESS_LAB_EMAIL", "consultor@nexyra.lab"),
        help="Usuário informado no contexto do widget.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/business_lab_benchmark",
        help="Pasta de saída dos relatórios.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    module = _load_visual_validation_module()

    validator = module.AtlasCopilotVisualValidator(
        business_lab_url=args.business_lab_url,
        atlas_bridge_url=args.atlas_bridge_url,
        copilot_token=args.token,
        lead_code=args.lead_code,
        user_email=args.user_email,
    )
    report = validator.run()
    json_path, md_path = module.save_visual_validation_report(
        report,
        output_dir=Path(args.output_dir),
    )

    status = "APROVADO" if report.passed else "REPROVADO"
    print("Atlas Copilot — Validação final visual")
    print(f"Resultado: {status}")
    print(f"Etapas: {report.passed_steps}/{report.total_steps}")
    print(f"Tempo total: {report.total_elapsed_ms:.2f} ms")
    print()
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    print()

    for step in report.steps:
        marker = "OK" if step.ok else "FALHOU"
        print(f"{step.step_id} [{marker}] {step.name} ({step.elapsed_ms:.2f} ms)")
        if step.answer:
            print(f"  Resposta: {step.answer}")
        if step.error:
            print(f"  Erro: {step.error}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
