from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    ProvisioningExecutor,
    ProvisioningPlanner,
    ProvisioningProfile,
    ProvisioningService,
    ProvisioningStatus,
    build_provisioning_guard,
    build_provisioning_principal,
)


class _Collector:
    def __init__(self, inventory: DeviceInventory) -> None:
        self.inventory = inventory
        self.calls = 0

    def capture(self, packages=()):
        del packages
        self.calls += 1
        return self.inventory


def _inventory() -> DeviceInventory:
    return DeviceInventory(
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        device_hash=sha256(b"device").hexdigest(),
        winget_available=True,
    )


def _service(
    tmp_path: Path,
) -> tuple[ProvisioningService, _Collector]:
    collector = _Collector(_inventory())
    profile = ProvisioningProfile(
        profile_id="school-sales",
        display_name="Vendas",
        directories=(
            DirectoryRequirement(
                relative_path="Escola/Leads",
                description="Criar pasta de leads",
            ),
        ),
    )
    service = ProvisioningService(
        guard=build_provisioning_guard(),
        collector=collector,
        planner=ProvisioningPlanner(),
        executor=ProvisioningExecutor(tmp_path, dry_run=True),
        profiles=(profile,),
    )
    return service, collector


def test_service_requires_confirmation_and_rechecks_inventory(
    tmp_path: Path,
) -> None:
    service, collector = _service(tmp_path)
    principal = build_provisioning_principal()

    approval = service.prepare("school-sales", principal)

    assert approval.confirmation_token is not None
    assert collector.calls == 1

    evidence = service.confirm(approval.confirmation_token, principal)

    assert evidence.status is ProvisioningStatus.DRY_RUN
    assert collector.calls == 2


def test_service_blocks_plan_when_inventory_changed(
    tmp_path: Path,
) -> None:
    service, collector = _service(tmp_path)
    principal = build_provisioning_principal()
    approval = service.prepare("school-sales", principal)
    collector.inventory = replace(
        collector.inventory,
        os_version="11.1",
    )

    with pytest.raises(PermissionError, match="mudou"):
        service.confirm(approval.confirmation_token, principal)


def test_confirmation_is_single_use(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    principal = build_provisioning_principal()
    approval = service.prepare("school-sales", principal)
    service.confirm(approval.confirmation_token, principal)

    with pytest.raises(ValueError, match="não existe"):
        service.confirm(approval.confirmation_token, principal)
