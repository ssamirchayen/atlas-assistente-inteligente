"""Piloto seguro do inventário LGPD: usa somente metadados técnicos."""

from __future__ import annotations

import argparse
from pathlib import Path

from atlas.privacy import build_default_privacy_inventory


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exibe o inventário técnico de privacidade do Atlas.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Exporta uma cópia JSON sem conteúdo real de titulares.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Retorna código 2 enquanto houver lacunas altas ou críticas.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    inventory = build_default_privacy_inventory()
    report = inventory.analyze()

    print("Atlas — Sprint 24, Etapa 1: Inventário LGPD")
    print(f"Operações de tratamento mapeadas: {report.total_records}")
    print("Risco técnico preliminar:")
    for risk, count in sorted(report.counts_by_risk.items()):
        print(f"- {risk}: {count}")
    print(f"Lacunas altas ou críticas: {report.high_or_critical_issues}")
    print("Nenhum conteúdo pessoal, áudio, imagem, token ou telefone foi lido.")

    if args.json is not None:
        target = inventory.export_json(args.json)
        print(f"Inventário exportado para: {target}")

    if args.strict and report.high_or_critical_issues:
        print("Modo estrito: existem decisões ou controles pendentes.")
        return 2

    print("Inventário estrutural concluído; pendências permanecem explícitas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
