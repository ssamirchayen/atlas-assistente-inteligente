from __future__ import annotations

from hashlib import sha256

import pytest

from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    PackageRequirement,
    ProvisioningPlanner,
    ProvisioningProfile,
    ProvisioningStepType,
)


def _inventory(
    *,
    winget: bool = True,
    installed: frozenset[str] = frozenset(),
) -> DeviceInventory:
    return DeviceInventory(
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        device_hash=sha256(b"device").hexdigest(),
        winget_available=winget,
        installed_package_ids=installed,
    )


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="school-sales",
        display_name="Vendas",
        packages=(
            PackageRequirement(
                package_id="Google.Chrome",
                display_name="Google Chrome",
            ),
        ),
        directories=(
            DirectoryRequirement(
                relative_path="Escola/Leads",
                description="Criar pasta de leads",
            ),
        ),
    )


def test_planner_skips_already_installed_package() -> None:
    plan = ProvisioningPlanner().build(
        _profile(),
        _inventory(installed=frozenset({"Google.Chrome"})),
    )

    assert len(plan.steps) == 1
    assert plan.steps[0].step_type is ProvisioningStepType.CREATE_DIRECTORY


def test_planner_rejects_missing_winget_when_package_is_needed() -> None:
    with pytest.raises(ValueError, match="WinGet"):
        ProvisioningPlanner().build(
            _profile(),
            _inventory(winget=False),
        )


def test_planner_rejects_non_windows_device() -> None:
    inventory = DeviceInventory(
        os_name="Linux",
        os_version="1",
        architecture="x86_64",
        device_hash=sha256(b"device").hexdigest(),
        winget_available=False,
    )

    with pytest.raises(ValueError, match="Windows"):
        ProvisioningPlanner().build(_profile(), inventory)
