"""Piloto local e não destrutivo do Resource Manager."""

from __future__ import annotations

from atlas.core.config import ATLAS_RUNTIME_PROFILE, ROOT_DIR
from atlas.core.resource_manager import ResourceManager, WorkloadClass
from atlas.core.runtime_profile import RuntimeProfileService


def main() -> None:
    profile = RuntimeProfileService(project_root=ROOT_DIR).resolve(
        ATLAS_RUNTIME_PROFILE
    )
    manager = ResourceManager(profile=profile)
    before = manager.status()

    print("Sprint 25 — Etapa 2: Resource Manager")
    print(f"Perfil: {before.profile.value}")
    print(f"Pressão: {before.pressure.value}")
    print(f"Capacidade: {before.active_leases}/{before.capacity}")
    print(
        "CPU/RAM: "
        f"{before.metrics.cpu_percent}%/{before.metrics.memory_percent}%"
    )

    admission = manager.try_acquire(WorkloadClass.STANDARD)
    print(f"Admissão simulada: {admission.outcome.value}")
    if admission.lease is not None:
        manager.release(admission.lease.lease_id)

    print(f"Licenças após liberação: {manager.active_lease_count}")
    print(f"Eventos locais: {len(manager.audit_events())}")
    print("Nenhum processo ou configuração do computador foi alterado.")


if __name__ == "__main__":
    main()
