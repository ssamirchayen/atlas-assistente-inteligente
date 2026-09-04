"""Diagnóstico seguro dos perfis do Atlas Core 1.0."""

from __future__ import annotations

import argparse

from atlas.core.config import ATLAS_RUNTIME_PROFILE, ROOT_DIR
from atlas.core.runtime_profile import RuntimeProfileService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mostra o perfil recomendado sem modificar o computador.",
    )
    parser.add_argument(
        "--profile",
        choices=("auto", "lite", "standard", "full"),
        default=ATLAS_RUNTIME_PROFILE,
        help="Perfil solicitado apenas para esta execução.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    decision = RuntimeProfileService(project_root=ROOT_DIR).resolve(args.profile)
    summary = decision.public_summary()

    print("Sprint 25 — Etapa 1: perfil e recursos")
    print(f"Solicitado: {summary['requested']}")
    print(f"Recomendado: {summary['recommended']}")
    print(f"Selecionado: {summary['selected']}")
    print(f"Suporte: {summary['support_status']}")
    print(f"Fallback explícito: {summary['fallback_applied']}")
    print(
        "RAM total/disponível: "
        f"{summary['total_memory_gb']}/{summary['available_memory_gb']} GB"
    )
    print(f"CPUs lógicas: {summary['logical_cpus']}")
    print(f"Disco livre: {summary['disk_free_gb']} GB")
    print(f"VRAM detectada: {summary['gpu_vram_gb']} GB")
    print(
        "Limites preparados: "
        f"workers={decision.budget.worker_limit}, "
        f"tarefas={decision.budget.parallel_task_limit}, "
        f"contexto={decision.budget.model_context_limit}"
    )
    print("Nenhum processo, arquivo ou configuração foi alterado.")


if __name__ == "__main__":
    main()
