from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


def _ensure_project_root() -> None:
    project_root = Path(__file__).resolve().parents[1]
    root = str(project_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def main() -> int:
    _ensure_project_root()

    module = importlib.import_module(
        "atlas.integrations.business_lab"
    )
    bridge_class = module.BusinessLabBridge

    parser = argparse.ArgumentParser(
        description=(
            "Valida a conexão local Atlas -> Nexyra Business Lab."
        )
    )
    parser.add_argument(
        "--url",
        default=None,
        help=(
            "URL do Business Lab. Padrão: "
            "ATLAS_BUSINESS_LAB_URL ou http://127.0.0.1:5055"
        ),
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_browser",
        help="Abre a tela de login após validar a conexão.",
    )
    args = parser.parse_args()

    bridge = bridge_class(args.url)
    health = bridge.health()

    print("Atlas -> Nexyra Business Lab")
    print(f"URL: {bridge.base_url}")
    print(f"Alcançável: {health.reachable}")
    print(f"Status: {health.status}")
    print(f"Serviço: {health.service}")
    print(f"Versão: {health.version}")
    print(f"Schema: {health.schema_version}")

    if health.error:
        print(f"Erro: {health.error}")

    if not health.reachable:
        print(
            "\nFalha: inicie o Business Lab antes de executar "
            "a integração."
        )
        return 1

    if args.open_browser:
        bridge.open_login()
        print("\nTela de login aberta no navegador.")

    print("\nConexão básica validada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
