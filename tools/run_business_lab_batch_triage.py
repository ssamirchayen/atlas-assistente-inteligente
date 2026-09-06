from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    bridge_module = importlib.import_module("atlas.copilot.business_lab")
    bridge = bridge_module.BusinessLabCopilotBridge()
    response = bridge.handle(
        {
            "message": (
                "Atlas, analise os 10 leads novos de Radiologia, "
                "priorize os mais importantes e sugira a próxima ação."
            ),
            "context": {
                "page": "leads_list",
                "route": "/leads",
                "user_email": "consultor@nexyra.lab",
            },
            "dry_run": True,
        }
    )

    payload: dict[str, Any] = response.to_api_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
