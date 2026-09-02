"""Safe restart and supervised execution pilot for Sprint 23 Stage 3."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.edge import (
    EdgeExecutionService,
    EdgeProfileService,
    EdgeStateStore,
    EdgeTaskQueue,
    EdgeTaskStore,
    EmployeeProfileCatalog,
    ITProvisioningAgent,
)
from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    ManagedSettingRequirement,
    ManagedSettingType,
    PackageRequirement,
    ProvisioningExecutor,
    ProvisioningPlanner,
    ProvisioningProfile,
)


class _SyntheticWindowsInventory:
    def capture(self, packages=()):
        del packages
        return DeviceInventory(
            os_name="Windows",
            os_version="11-piloto",
            architecture="AMD64",
            device_hash=sha256(b"atlas-edge-stage3-pilot").hexdigest(),
            winget_available=True,
            captured_at=datetime.now(timezone.utc),
        )


def _pilot_profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-pilot",
        display_name="Funcionário corporativo — piloto",
        packages=(
            PackageRequirement("Google.Chrome", "Google Chrome"),
        ),
        directories=(
            DirectoryRequirement(
                "Empresa/Piloto",
                "Criar workspace temporário do perfil",
            ),
        ),
        settings=(
            ManagedSettingRequirement(
                setting_id="browser-home",
                setting_type=ManagedSettingType.BROWSER,
                description="Definir página inicial corporativa",
                parameters={
                    "browser": "chrome",
                    "homepage": "https://portal.empresa.test",
                },
            ),
            ManagedSettingRequirement(
                setting_id="printer-office",
                setting_type=ManagedSettingType.PRINTER,
                description="Conectar impressora corporativa",
                parameters={"connection_name": r"\\print-srv\Escritorio"},
            ),
            ManagedSettingRequirement(
                setting_id="vpn-office",
                setting_type=ManagedSettingType.VPN,
                description="Criar perfil de VPN corporativa",
                parameters={
                    "name": "VPN Empresa",
                    "server": "vpn.empresa.test",
                    "tunnel_type": "ikev2",
                    "split_tunnel": "false",
                },
            ),
            ManagedSettingRequirement(
                setting_id="network-office",
                setting_type=ManagedSettingType.NETWORK,
                description="Aplicar perfil de rede corporativa",
                parameters={
                    "profile": "Rede Empresa",
                    "mode": "corporate",
                },
            ),
        ),
    )


def _confirm(message: str) -> bool:
    print(message)
    return input("> ").strip() == "SIM"


def main() -> int:
    print("Atlas Edge — piloto seguro da Sprint 23, Etapa 3")
    print("Fila, reinício e execução serão simulados em uma pasta temporária.")
    collector = _SyntheticWindowsInventory()

    with TemporaryDirectory(prefix="atlas-edge-execution-pilot-") as directory:
        root = Path(directory)
        agent = ITProvisioningAgent(
            store=EdgeStateStore(root / "device.json"),
            collector=collector,
        )
        enrollment = agent.prepare_enrollment("empresa-piloto")
        if not _confirm("Digite SIM para cadastrar o dispositivo temporário."):
            print("Piloto cancelado sem alterações.")
            return 1
        agent.confirm_enrollment(
            enrollment.token,
            approver_id="ti.cadastro",
        )

        catalog = EmployeeProfileCatalog((_pilot_profile(),))
        planner = ProvisioningPlanner()
        profiles = EdgeProfileService(
            agent=agent,
            collector=collector,
            planner=planner,
            catalog=catalog,
        )
        challenge = profiles.prepare_configuration(
            "employee-pilot",
            employee_reference="funcionario-piloto",
            requester_id="ti.operador",
        )
        print("Plano declarativo:")
        for step in challenge.preview.plan.steps:
            print(f"- {step.step_type.value}: {step.description}")
        if not _confirm("Digite SIM para autorizar o plano revisado."):
            print("Plano cancelado sem execução.")
            return 1
        authorization = profiles.authorize_configuration(
            challenge.token,
            approver_id="ti.responsavel",
        )

        store = EdgeTaskStore(root / "tasks.json")
        queue = EdgeTaskQueue(store)
        service = EdgeExecutionService(
            agent=agent,
            profile_service=profiles,
            queue=queue,
            catalog=catalog,
            collector=collector,
            planner=planner,
            executor=ProvisioningExecutor(
                root / "workspace",
                dry_run=True,
            ),
        )
        task = service.enqueue_authorization(authorization.authorization_id)
        queue.claim(task.task_id)
        resumed_queue = EdgeTaskQueue(store)
        resumed = resumed_queue.get(task.task_id)
        print(
            f"Retomada simulada: {resumed.status.value} | "
            f"recuperações={resumed.recovery_count}"
        )
        resumed_service = EdgeExecutionService(
            agent=agent,
            profile_service=profiles,
            queue=resumed_queue,
            catalog=catalog,
            collector=collector,
            planner=planner,
            executor=ProvisioningExecutor(
                root / "workspace",
                dry_run=True,
            ),
        )
        if not _confirm("Digite SIM para executar a simulação supervisionada."):
            resumed_service.cancel_task(task.task_id)
            print("Tarefa cancelada sem alterações.")
            return 1
        result = resumed_service.execute_task(task.task_id)
        print(
            f"Tarefa {result.task.status.value}: "
            f"{len(result.evidence.steps)} etapas simuladas."
        )

    print("Piloto concluído. Nenhum programa ou configuração foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
