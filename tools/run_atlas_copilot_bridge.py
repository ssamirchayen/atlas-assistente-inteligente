from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Executa a API local do Atlas Copilot Bridge.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host local. Use 127.0.0.1 por segurança.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Porta local do Copilot Bridge.",
    )
    args = parser.parse_args()

    local_api = importlib.import_module("atlas.copilot.local_api")
    local_api.run_copilot_server(
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
