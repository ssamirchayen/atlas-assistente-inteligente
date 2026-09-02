"""Adapters for enterprise-specific Windows settings."""

from __future__ import annotations

from typing import Protocol

from atlas.provisioning.models import ProvisioningStep


class ManagedSettingsAdapter(Protocol):
    """Company adapter boundary for reviewed browser/device/network settings."""

    def apply(self, step: ProvisioningStep) -> str: ...


class BlockedManagedSettingsAdapter:
    """Fail-closed default until the company installs a reviewed adapter."""

    def apply(self, step: ProvisioningStep) -> str:
        del step
        raise PermissionError(
            "A configuração exige um adaptador corporativo revisado."
        )
