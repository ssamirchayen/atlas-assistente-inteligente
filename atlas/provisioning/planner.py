"""Gera planos declarativos a partir do perfil e do inventário."""

from __future__ import annotations

from atlas.provisioning.models import (
    DeviceInventory,
    ManagedSettingType,
    ProvisioningPlan,
    ProvisioningProfile,
    ProvisioningStep,
    ProvisioningStepType,
)


class NothingToProvisionError(ValueError):
    """O computador já satisfaz o perfil solicitado."""


class ProvisioningPlanner:
    """Cria somente etapas conhecidas; nunca aceita scripts livres."""

    def build(
        self,
        profile: ProvisioningProfile,
        inventory: DeviceInventory,
    ) -> ProvisioningPlan:
        if inventory.os_name.casefold() != "windows":
            raise ValueError("O provisionamento desta etapa exige Windows.")

        steps: list[ProvisioningStep] = []

        for index, directory in enumerate(profile.directories, start=1):
            steps.append(
                ProvisioningStep(
                    step_id=f"folder-{index}",
                    step_type=ProvisioningStepType.CREATE_DIRECTORY,
                    description=directory.description,
                    parameters={"relative_path": directory.relative_path},
                    reversible=True,
                )
            )

        missing_packages = tuple(
            package
            for package in profile.packages
            if package.package_id not in inventory.installed_package_ids
        )

        if missing_packages and not inventory.winget_available:
            raise ValueError(
                "O WinGet não está disponível para instalar os pacotes."
            )

        for index, package in enumerate(missing_packages, start=1):
            steps.append(
                ProvisioningStep(
                    step_id=f"package-{index}",
                    step_type=(
                        ProvisioningStepType.INSTALL_WINGET_PACKAGE
                    ),
                    description=f"Instalar {package.display_name}",
                    parameters={
                        "package_id": package.package_id,
                        "source": package.source,
                    },
                    reversible=False,
                )
            )

        setting_step_types = {
            ManagedSettingType.BROWSER: ProvisioningStepType.CONFIGURE_BROWSER,
            ManagedSettingType.PRINTER: ProvisioningStepType.CONNECT_PRINTER,
            ManagedSettingType.VPN: ProvisioningStepType.CONFIGURE_VPN,
            ManagedSettingType.NETWORK: ProvisioningStepType.CONFIGURE_NETWORK,
        }
        for index, setting in enumerate(profile.settings, start=1):
            steps.append(
                ProvisioningStep(
                    step_id=f"setting-{index}",
                    step_type=setting_step_types[setting.setting_type],
                    description=setting.description,
                    parameters={
                        "setting_id": setting.setting_id,
                        **dict(setting.parameters),
                    },
                    reversible=False,
                )
            )

        if not steps:
            raise NothingToProvisionError(
                "O computador já atende ao perfil solicitado."
            )

        return ProvisioningPlan(
            profile_id=profile.profile_id,
            inventory_fingerprint=inventory.fingerprint(),
            steps=tuple(steps),
        )
