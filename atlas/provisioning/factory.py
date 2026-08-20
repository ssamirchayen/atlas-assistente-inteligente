"""Composição padrão dos perfis corporativos de provisionamento."""

from __future__ import annotations

from atlas.connectors import (
    ConnectorCapability,
    ConnectorGuard,
    ConnectorManifest,
    ConnectorPrincipal,
    ConnectorRegistry,
    ConnectorRisk,
)
from atlas.core.config import (
    PROVISIONING_COMMAND_TIMEOUT,
    PROVISIONING_DRY_RUN,
    PROVISIONING_MAX_STEPS,
    PROVISIONING_WORKSPACE,
    USER_NAME,
)
from atlas.provisioning.executor import ProvisioningExecutor
from atlas.provisioning.inventory import DeviceInventoryCollector
from atlas.provisioning.models import (
    DirectoryRequirement,
    PackageRequirement,
    ProvisioningProfile,
)
from atlas.provisioning.planner import ProvisioningPlanner
from atlas.provisioning.service import ProvisioningService


def build_provisioning_profiles() -> tuple[ProvisioningProfile, ...]:
    """Perfis declarativos iniciais, sem credenciais ou scripts livres."""

    common_packages = (
        PackageRequirement(
            package_id="Google.Chrome",
            display_name="Google Chrome",
        ),
        PackageRequirement(
            package_id="Microsoft.Teams",
            display_name="Microsoft Teams",
        ),
        PackageRequirement(
            package_id="Adobe.Acrobat.Reader.64-bit",
            display_name="Adobe Acrobat Reader",
        ),
    )
    return (
        ProvisioningProfile(
            profile_id="school-sales",
            display_name="Atendimento e vendas da escola",
            packages=common_packages,
            directories=(
                DirectoryRequirement(
                    relative_path="Escola/Leads",
                    description="Criar pasta local de trabalho com leads",
                ),
                DirectoryRequirement(
                    relative_path="Escola/Documentos",
                    description="Criar pasta local de documentos",
                ),
            ),
        ),
        ProvisioningProfile(
            profile_id="school-helpdesk",
            display_name="Suporte de TI da escola",
            packages=common_packages
            + (
                PackageRequirement(
                    package_id="7zip.7zip",
                    display_name="7-Zip",
                ),
                PackageRequirement(
                    package_id="Microsoft.PowerToys",
                    display_name="Microsoft PowerToys",
                ),
            ),
            directories=(
                DirectoryRequirement(
                    relative_path="TI/Atendimentos",
                    description="Criar pasta de evidências de atendimento",
                ),
            ),
        ),
    )


def build_provisioning_guard() -> ConnectorGuard:
    manifest = ConnectorManifest(
        connector_id="device.provisioning",
        display_name="Provisionamento de computadores",
        description="Inventário e aplicação de perfis Windows aprovados.",
        capabilities=(
            ConnectorCapability(
                name="inventory",
                required_scope="devices:inventory:read",
                risk=ConnectorRisk.READ_ONLY,
            ),
            ConnectorCapability(
                name="apply_plan",
                required_scope="devices:provision:apply",
                risk=ConnectorRisk.EXTERNAL_WRITE,
            ),
        ),
        max_batch_size=PROVISIONING_MAX_STEPS,
        operations_per_minute=30,
    )
    return ConnectorGuard(ConnectorRegistry((manifest,)))


def build_provisioning_principal() -> ConnectorPrincipal:
    return ConnectorPrincipal(
        principal_id=USER_NAME,
        role="device_operator",
        scopes=frozenset(
            {
                "devices:inventory:read",
                "devices:provision:apply",
            }
        ),
    )


def build_default_provisioning_service() -> ProvisioningService:
    collector = DeviceInventoryCollector(
        timeout=PROVISIONING_COMMAND_TIMEOUT,
    )
    executor = ProvisioningExecutor(
        PROVISIONING_WORKSPACE,
        command_timeout=PROVISIONING_COMMAND_TIMEOUT,
        dry_run=PROVISIONING_DRY_RUN,
    )
    return ProvisioningService(
        guard=build_provisioning_guard(),
        collector=collector,
        planner=ProvisioningPlanner(),
        executor=executor,
        profiles=build_provisioning_profiles(),
    )
