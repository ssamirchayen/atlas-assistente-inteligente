"""Safe local pilot for Sprint 23 Stage 2."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.edge import (
    EdgeProfileService,
    EdgeStateStore,
    EmployeeProfileCatalog,
    ITProvisioningAgent,
)
from atlas.provisioning import DeviceInventory, ProvisioningPlanner
from atlas.provisioning.factory import build_provisioning_profiles


class _SyntheticWindowsInventory:
    """Deterministic test inventory; it never invokes WinGet or the shell."""

    def capture(self, packages=()):
        del packages
        return DeviceInventory(
            os_name="Windows",
            os_version="11-piloto",
            architecture="AMD64",
            device_hash=sha256(b"atlas-edge-stage2-pilot").hexdigest(),
            winget_available=True,
            captured_at=datetime.now(timezone.utc),
        )


def main() -> int:
    print("Atlas Edge — piloto seguro da Sprint 23, Etapa 2")
    print("O piloto usa inventário sintético e não executa nenhuma etapa.")
    collector = _SyntheticWindowsInventory()

    with TemporaryDirectory(prefix="atlas-edge-profile-pilot-") as directory:
        agent = ITProvisioningAgent(
            store=EdgeStateStore(Path(directory) / "device.json"),
            collector=collector,
        )
        enrollment = agent.prepare_enrollment("empresa-piloto")
        print("Digite SIM para cadastrar o dispositivo temporário.")
        if input("> ").strip() != "SIM":
            print("Piloto cancelado sem alterações.")
            return 1
        agent.confirm_enrollment(
            enrollment.token,
            approver_id="ti.cadastro",
        )

        service = EdgeProfileService(
            agent=agent,
            collector=collector,
            planner=ProvisioningPlanner(),
            catalog=EmployeeProfileCatalog(build_provisioning_profiles()),
        )
        print("Perfis autorizados:")
        for profile in service.list_profiles():
            print(
                f"- {profile.profile_id}: {profile.display_name} "
                f"({profile.package_count} programas, "
                f"{profile.directory_count} pastas)"
            )

        challenge = service.prepare_configuration(
            "school-sales",
            employee_reference="funcionario-piloto",
            requester_id="ti.operador",
        )
        print("Plano preparado para school-sales:")
        for step in challenge.preview.plan.steps:
            print(f"- {step.step_type.value}: {step.description}")
        print("Digite SIM para autorizar o plano sem executá-lo.")
        if input("> ").strip() != "SIM":
            print("Autorização cancelada sem alterações.")
            return 1
        authorized = service.authorize_configuration(
            challenge.token,
            approver_id="ti.responsavel",
        )
        print(f"Plano autorizado: {authorized.authorization_id}")

    print("Piloto concluído. Nenhuma etapa do plano foi executada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
