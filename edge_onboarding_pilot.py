"""Safe end-to-end employee onboarding pilot for Sprint 23 Stage 5."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from atlas.edge import (
    EdgeExecutionService,
    EdgePolicyEngine,
    EdgePrincipal,
    EdgeProfileService,
    EdgeRole,
    EdgeStateStore,
    EdgeTaskQueue,
    EdgeTaskStore,
    EmployeeOnboardingService,
    EmployeeOnboardingStore,
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
            device_hash=sha256(b"atlas-edge-onboarding-pilot").hexdigest(),
            winget_available=True,
            captured_at=datetime.now(timezone.utc),
        )


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-onboarding-pilot",
        display_name="Novo funcionário — piloto",
        packages=(PackageRequirement("Google.Chrome", "Google Chrome"),),
        directories=(
            DirectoryRequirement("Empresa/NovoFuncionario", "Workspace"),
        ),
        settings=(
            ManagedSettingRequirement(
                setting_id="browser-home",
                setting_type=ManagedSettingType.BROWSER,
                description="Página inicial corporativa",
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
    print("Atlas Edge — Sprint 23, Etapa 5")
    print("Piloto completo de onboarding em pasta temporária e dry-run.")
    if not _confirm("Digite SIM para cadastrar o dispositivo temporário."):
        print("Piloto cancelado sem alterações.")
        return 1

    collector = _SyntheticInventory()
    profile = _profile()
    with TemporaryDirectory(prefix="atlas-edge-onboarding-") as directory:
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
        onboarding = EmployeeOnboardingService(
            governed=governed,
            store=EmployeeOnboardingStore(root / "onboardings.json"),
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
        started = onboarding.start(
            operator,
            profile.profile_id,
            employee_reference="funcionario-piloto",
        )
        print(f"Onboarding: {started.onboarding.onboarding_id}")
        print("Plano do novo funcionário:")
        for step in started.preview.plan.steps:
            print(f"- {step.step_type.value}: {step.description}")
        if not _confirm("Digite SIM para o aprovador autorizar o plano."):
            onboarding.cancel(operator, started.onboarding.onboarding_id)
            print("Onboarding cancelado sem execução.")
            return 1
        approved = onboarding.approve(
            approver,
            started.onboarding.onboarding_id,
        )
        queued = onboarding.enqueue(operator, approved.onboarding_id)
        print(f"Tarefa persistente: {queued.task_id}")
        if not _confirm("Digite SIM para o executor realizar o dry-run."):
            onboarding.cancel(operator, queued.onboarding_id)
            print("Tarefa cancelada sem alterações.")
            return 1
        completed = onboarding.execute(executor, queued.onboarding_id)
        auditor = EdgePrincipal(
            "ti.auditor",
            "empresa-piloto",
            EdgeRole.AUDITOR,
        )
        report = onboarding.report(auditor)
        print(
            f"Resultado: {completed.status.value}; "
            f"simulados no relatório: {report.simulated}; "
            f"eventos auditados: {len(audit.events)}."
        )

    print("Sprint 23 concluída. Nenhum programa ou configuração foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
