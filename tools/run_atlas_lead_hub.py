from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.lead_hub.service import LeadHubService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Atlas Lead Hub runner")
    parser.add_argument(
        "--command",
        default="Atlas, puxe os leads da internet, organize no sistema e prepare contato.",
        help="Comando em linguagem natural para o Atlas.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Usa leads demo autorizados para validar a automação local.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Mostra resposta completa em JSON.",
    )
    args = parser.parse_args()

    result = LeadHubService().run_from_command(args.command, demo=args.demo)
    print(result.message)
    if args.json:
        print(json.dumps(result.payload, indent=2, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
