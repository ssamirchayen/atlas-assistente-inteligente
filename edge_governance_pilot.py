"""Safe RBAC and audit pilot for Sprint 23 Stage 4."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.edge import (
    EdgeExecutionService,
    EdgePolicyDenied,
    EdgePolicyEngine,
    EdgePrincipal,
    EdgeProfileService,
    EdgeRole,
    EdgeStateStore,
    EdgeTaskQueue,
    EdgeTaskStore,
    EmployeeProfileCatalog,
    GovernedEdgeService,
    ITProvisioningAgent,
    InMemoryEdgeAuditTrail,
    build_edge_policy,
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


class _SyntheticInventory:
    def capture(self, packages=()):
        del packages
        return DeviceInventory(
            os_name="Windows",
            os_version="11-piloto",
            architecture="AMD64",
            device_hash=sha256(b"atlas-edge-governance-pilot").hexdigest(),
            winget_available=True,
            captured_at=datetime.now(timezone.utc),
        )


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-governance-pilot",
        display_name="Funcionário — piloto governado",
        packages=(PackageRequirement("Google.Chrome", "Google Chrome"),),
        directories=(
            DirectoryRequirement("Empresa/Piloto", "Workspace corporativo"),
        ),
        settings=(
            ManagedSettingRequirement(
                setting_id="browser-home",
                setting_type=ManagedSettingType.BROWSER,
                description="Definir página corporativa",
                parameters={
                    "browser": "chrome",
                    "homepage": "https://portal.empresa.test",
                },
            ),
        ),
    )


def _confirm(message: str) -> bool:
    print(message)
    return input("> ").strip() == "SIM"


def main() -> int:
    print("Atlas Edge — Sprint 23, Etapa 4")
    print("Piloto temporário de permissões, isolamento e auditoria.")
    if not _confirm("Digite SIM para iniciar o piloto sem efeitos reais."):
        print("Piloto cancelado sem alterações.")
        return 1

    collector = _SyntheticInventory()
    profile = _profile()
    with TemporaryDirectory(prefix="atlas-edge-governance-") as directory:
        root = Path(directory)
        agent = ITProvisioningAgent(
            store=EdgeStateStore(root / "device.json"),
            collector=collector,
        )
        enrollment = agent.prepare_enrollment("empresa-piloto")
        agent.confirm_enrollment(enrollment.token, approver_id="ti.cadastro")
        catalog = EmployeeProfileCatalog((profile,))
        planner = ProvisioningPlanner()
        profiles = EdgeProfileService(
            agent=agent,
            collector=collector,
            planner=planner,
            catalog=catalog,
        )
        execution = EdgeExecutionService(
            agent=agent,
            profile_service=profiles,
            queue=EdgeTaskQueue(EdgeTaskStore(root / "tasks.json")),
            catalog=catalog,
            collector=collector,
            planner=planner,
            executor=ProvisioningExecutor(root / "workspace", dry_run=True),
        )
        audit = InMemoryEdgeAuditTrail()
        governed = GovernedEdgeService(
            agent=agent,
            profile_service=profiles,
            execution_service=execution,
            policy=EdgePolicyEngine(
                (build_edge_policy("empresa-piloto", (profile,)),)
            ),
            audit=audit,
        )
        operator = EdgePrincipal(
            "ti.operador",
            "empresa-piloto",
            EdgeRole.OPERATOR,
        )
        approver = EdgePrincipal(
            "ti.aprovador",
            "empresa-piloto",
            EdgeRole.APPROVER,
        )
        executor = EdgePrincipal(
            "ti.executor",
            "empresa-piloto",
            EdgeRole.EXECUTOR,
        )
        outsider = EdgePrincipal(
            "ti.externo",
            "outra-empresa",
            EdgeRole.ADMIN,
        )
        try:
            governed.list_profiles(outsider)
        except EdgePolicyDenied as error:
            print(f"Isolamento confirmado: {error.reason_code}")

        challenge = governed.prepare_configuration(
            operator,
            profile.profile_id,
            employee_reference="funcionario-piloto",
        )
        print("Plano permitido pela política:")
        for step in challenge.preview.plan.steps:
            print(f"- {step.step_type.value}: {step.description}")
        if not _confirm("Digite SIM para o aprovador autorizar esse plano."):
            print("Plano cancelado sem execução.")
            return 1
        authorization = governed.authorize_configuration(
            approver,
            challenge.token,
        )
        task = governed.enqueue_authorization(
            operator,
            authorization.authorization_id,
        )
        if not _confirm("Digite SIM para o executor realizar o dry-run."):
            governed.cancel_task(operator, task.task_id)
            print("Tarefa cancelada sem alterações.")
            return 1
        result = governed.execute_task(executor, task.task_id)
        auditor = EdgePrincipal(
            "ti.auditor",
            "empresa-piloto",
            EdgeRole.AUDITOR,
        )
        events = governed.list_audit(auditor)
        print(
            f"Resultado: {result.task.status.value}; "
            f"eventos auditados: {len(events)}."
        )

    print("Piloto concluído. Nenhum programa ou configuração foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
