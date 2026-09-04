"""Piloto local da Sprint 25, Etapa 4, sem carregar modelos reais."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from atlas.brain.model_router import (
    ModelCandidate,
    ModelRouter,
    ModelTask,
    ModelTier,
    StaticModelInventory,
)
from atlas.core.resource_manager import ResourcePressure
from atlas.core.runtime_profile import HardwareSnapshot, RuntimeProfileSelector


def build_router(profile_name: str, pressure: ResourcePressure) -> ModelRouter:
    hardware = HardwareSnapshot(
        captured_at=datetime.now(timezone.utc),
        total_memory_gb=32,
        available_memory_gb=16,
        logical_cpus=16,
        physical_cpus=8,
        disk_free_gb=100,
        gpu_vram_gb=12,
    )
    profile = RuntimeProfileSelector().select(hardware, profile_name)
    status = SimpleNamespace(
        status=lambda: SimpleNamespace(pressure=pressure)
    )
    return ModelRouter(
        profile=profile,
        candidates=(
            ModelCandidate("demo-lite", ModelTier.LITE, 7, 1, 4096),
            ModelCandidate("demo-standard", ModelTier.BALANCED, 14, 2.5, 8192),
            ModelCandidate("demo-full", ModelTier.LARGE, 28, 6, 16384, 8),
        ),
        fallback_model="demo-lite",
        inventory=StaticModelInventory(
            {"demo-lite", "demo-standard", "demo-full"}
        ),
        resource_status=status,
    )


def main() -> None:
    print("Sprint 25 — Etapa 4: Model Router")
    scenarios = (
        ("lite", ModelTask.CHAT, ResourcePressure.NORMAL),
        ("standard", ModelTask.PLANNING, ResourcePressure.NORMAL),
        ("full", ModelTask.CODING, ResourcePressure.NORMAL),
        ("full", ModelTask.CODING, ResourcePressure.WARNING),
        ("full", ModelTask.ANALYSIS, ResourcePressure.CRITICAL),
    )
    for profile_name, task, pressure in scenarios:
        decision = build_router(profile_name, pressure).route(task)
        print(
            f"{profile_name:8} | {task.value:8} | {pressure.value:8} "
            f"-> {decision.model_name} ({decision.context_limit})"
        )
    print("Nenhum modelo foi carregado e nenhuma chamada de rede foi realizada.")


if __name__ == "__main__":
    main()

