"""Consulta o Nexyra usando a mesma configuração e cliente da conversa."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Carrega o .env pelo resolvedor oficial (inclui configuração do Atlas instalado).
from atlas.core import config as _atlas_config  # noqa: E402, F401
from atlas.integrations.nexyra_crm.commands import format_response  # noqa: E402
from atlas.integrations.nexyra_crm.connector import NexyraApiDriver  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico e consultas Nexyra CRM.")
    parser.add_argument(
        "--consulta",
        choices=("diagnostico", "resumo", "indicadores", "pendencias", "fontes"),
        default="diagnostico",
    )
    args = parser.parse_args()
    action = {
        "diagnostico": "diagnose",
        "resumo": "summary",
        "indicadores": "metrics",
        "pendencias": "pending",
        "fontes": "sources",
    }[args.consulta]
    result = NexyraApiDriver().execute(action)
    if not result.ok:
        print(f"Falha na consulta Nexyra: {result.error}")
        return 1
    print(format_response(action, result.data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
