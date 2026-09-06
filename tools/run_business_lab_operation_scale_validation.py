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


def _validation_module() -> Any:
    return importlib.import_module("atlas.copilot.operation_scale_validation")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida a operação em escala do Atlas no Nexyra Business Lab.",
    )
    parser.add_argument(
        "--business-lab-url",
        default=os.getenv("ATLAS_BUSINESS_LAB_URL", "http://127.0.0.1:5055"),
        help="URL local do Business Lab.",
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
        help="Lead usado para validações de contexto específico.",
    )
    parser.add_argument(
        "--user-email",
        default=os.getenv("ATLAS_BUSINESS_LAB_EMAIL", "consultor@nexyra.lab"),
        help="Usuário de referência enviado no contexto do widget.",
    )
    parser.add_argument(
        "--confirm-batch",
        action="store_true",
        help=(
            "Executa o lote confirmado no Business Lab. Sem essa flag, "
            "a etapa fica em modo seguro de prévia."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path("data") / "business_lab_benchmark"),
        help="Pasta onde salvar os relatórios JSON/Markdown.",
    )
    args = parser.parse_args()

    module = _validation_module()
    validator = module.AtlasOperationScaleValidator(
        business_lab_url=args.business_lab_url,
        atlas_bridge_url=args.atlas_bridge_url,
        copilot_token=args.token,
        lead_code=args.lead_code,
        user_email=args.user_email,
        confirm_batch=args.confirm_batch,
    )
    report = validator.run()
    json_path, md_path = module.save_operation_scale_validation_report(
        report,
        output_dir=args.output_dir,
    )

    status = "APROVADO" if report.passed else "REPROVADO"
    print("Atlas — Validação final da operação em escala")
    print(f"Resultado: {status}")
    print(f"Etapas: {report.passed_steps}/{report.total_steps}")
    print(f"Modo: {report.execution_mode}")
    print(f"Tempo total: {report.total_elapsed_ms:.2f} ms")
    print("")
    print("Capacidades:")
    for name, enabled in report.capabilities.items():
        marker = "OK" if enabled else "FALHOU"
        print(f"- {name}: {marker}")
    print("")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")

    if not report.passed:
        print("")
        print("Falhas:")
        for step in report.steps:
            if not step.ok:
                print(f"- {step.step_id} {step.name}: {step.error or step.answer}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
