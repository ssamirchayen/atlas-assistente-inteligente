from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

business_lab_module = importlib.import_module("atlas.copilot.business_lab")
BusinessLabCopilotBridge = business_lab_module.BusinessLabCopilotBridge

DEFAULT_OUTPUT_DIR = Path("data") / "business_lab_benchmark"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa prévia ou registro em lote no Business Lab pelo Atlas.",
    )
    parser.add_argument(
        "--message",
        default=(
            "Atlas, prepare mensagens para 10 leads novos de Radiologia "
            "e crie retornos para amanhã às 15h."
        ),
        help="Comando enviado ao Atlas Copilot.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "Registra os atendimentos/retornos no Business Lab. "
            "Sem isso, gera somente prévia segura."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Pasta para salvar a resposta JSON.",
    )
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "message": args.message,
        "context": {
            "page": "leads_list",
            "route": "/leads",
            "user_email": "consultor@nexyra.lab",
        },
    }
    if args.confirm:
        payload["confirmed"] = True

    bridge = BusinessLabCopilotBridge()
    response = bridge.handle(payload)
    api_payload = response.to_api_payload()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "executado" if args.confirm else "previa"
    output_path = args.output_dir / f"business_lab_batch_messages_{suffix}.json"
    output_path.write_text(
        json.dumps(api_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(response.answer)
    print()
    print(f"Resposta salva em: {output_path}")
    if not args.confirm:
        print()
        print(
            "Modo seguro: nada foi registrado. Para registrar no Business Lab, "
            "rode novamente com --confirm."
        )
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
