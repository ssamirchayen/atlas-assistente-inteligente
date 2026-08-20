"""Demonstração determinística de provisionamento; nunca altera o computador."""

from __future__ import annotations

from hashlib import sha256

from atlas.core.config import PROVISIONING_WORKSPACE
from atlas.provisioning import (
    DeviceInventory,
    ProvisioningExecutor,
    ProvisioningPlanner,
    ProvisioningService,
    build_provisioning_guard,
    build_provisioning_principal,
    build_provisioning_profiles,
)


class _DemoInventoryCollector:
    """Inventário fictício para provar o fluxo sem consultar o Windows."""

    def capture(self, packages=()):
        del packages
        return DeviceInventory(
            os_name="Windows",
            os_version="11-demo",
            architecture="AMD64",
            device_hash=sha256(b"atlas-provisioning-demo").hexdigest(),
            winget_available=True,
        )


def main() -> int:
    """Exibe, aprova e simula um plano declarativo."""

    profiles = build_provisioning_profiles()
    service = ProvisioningService(
        guard=build_provisioning_guard(),
        collector=_DemoInventoryCollector(),
        planner=ProvisioningPlanner(),
        executor=ProvisioningExecutor(
            PROVISIONING_WORKSPACE,
            dry_run=True,
        ),
        profiles=profiles,
    )
    principal = build_provisioning_principal()
    approval = service.prepare("school-sales", principal)

    print("\nPlano de demonstração para Atendimento e Vendas da escola:")
    for index, step in enumerate(approval.plan.steps, start=1):
        print(f"{index}. {step.description}")

    print("\nO piloto está travado em dry-run e não executará alterações.")
    confirmation = input(
        "Simular o plano? Digite SIM para confirmar: "
    ).strip()

    if confirmation != "SIM":
        print("Operação cancelada. O computador não foi alterado.")
        return 0

    token = approval.confirmation_token
    if token is None:
        raise RuntimeError("A confirmação obrigatória não foi emitida.")

    evidence = service.confirm(token, principal)
    print(
        "\nSimulação concluída. "
        f"Status: {evidence.status.value}; "
        f"etapas: {len(evidence.steps)}."
    )
    print("Nenhum programa ou pasta foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
