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
DEFAULT_MESSAGE = (
    "Atlas, gere um relatório completo dos leads, matrículas, atendimentos "
    "e retornos de Radiologia, apontando gargalos e próximas ações."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera relatório inteligente do Business Lab pelo Atlas.",
    )
    parser.add_argument(
        "--message",
        default=DEFAULT_MESSAGE,
        help="Comando de relatório enviado ao Atlas Copilot.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Pasta onde os relatórios serão salvos.",
    )
    args = parser.parse_args()

    payload: dict[str, Any] = {
        "message": args.message,
        "context": {
            "page": "reports",
            "route": "/relatorios",
            "user_email": "consultor@nexyra.lab",
        },
    }

    bridge = BusinessLabCopilotBridge()
    response = bridge.handle(payload)
    api_payload = response.to_api_payload()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_data = api_payload["data"]["data"] if response.ok else {}
    timestamp = report_data.get("report", {}).get("generated_at", "sem_data")
    safe_timestamp = str(timestamp).replace(":", "").replace("-", "")

    json_path = args.output_dir / f"business_lab_smart_report_{safe_timestamp}.json"
    json_path.write_text(
        json.dumps(api_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    exports = report_data.get("exports", {}) if isinstance(report_data, dict) else {}
    if isinstance(exports, dict):
        _write_export(
            args.output_dir / f"business_lab_smart_report_{safe_timestamp}.md",
            exports.get("markdown"),
        )
        _write_export(
            args.output_dir / f"business_lab_smart_report_{safe_timestamp}.csv",
            exports.get("csv"),
        )
        _write_export(
            args.output_dir / f"business_lab_smart_report_{safe_timestamp}.html",
            exports.get("html"),
        )

    print(response.answer)
    print()
    print(f"Relatório JSON salvo em: {json_path}")
    if response.ok:
        print(f"Relatórios Markdown/CSV/HTML salvos em: {args.output_dir}")
    return 0 if response.ok else 1


def _write_export(path: Path, content: Any) -> None:
    if isinstance(content, str) and content:
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
