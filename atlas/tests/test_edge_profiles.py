from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from atlas.edge import (
    EdgeConfigurationPreview,
    EmployeeProfileCatalog,
    hash_private_reference,
    profile_digest,
)
from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    PackageRequirement,
    ProvisioningPlanner,
    ProvisioningProfile,
)


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def _profile(profile_id: str = "employee-sales") -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id=profile_id,
        display_name="Equipe comercial",
        packages=(
            PackageRequirement(
                package_id="Google.Chrome",
                display_name="Google Chrome",
            ),
        ),
        directories=(
            DirectoryRequirement(
                relative_path="Empresa/Comercial",
                description="Criar workspace comercial",
            ),
        ),
    )


def _plan(profile: ProvisioningProfile):
    return ProvisioningPlanner().build(
        profile,
        DeviceInventory(
            os_name="Windows",
            os_version="11",
            architecture="AMD64",
            device_hash=sha256(b"device").hexdigest(),
            winget_available=True,
            captured_at=NOW,
        ),
    )


def test_catalog_lists_profiles_in_stable_order() -> None:
    first = _profile("employee-sales")
    second = _profile("employee-admin")
    catalog = EmployeeProfileCatalog((first, second))

    summaries = catalog.list()

    assert [item.profile_id for item in summaries] == [
        "employee-admin",
        "employee-sales",
    ]
    assert summaries[1].package_count == 1
    assert summaries[1].directory_count == 1
    assert summaries[1].profile_digest == profile_digest(first)


def test_catalog_rejects_duplicates_and_excess_requirements() -> None:
    profile = _profile()
    with pytest.raises(ValueError, match="IDs únicos"):
        EmployeeProfileCatalog((profile, profile))
    with pytest.raises(ValueError, match="limite de requisitos"):
        EmployeeProfileCatalog(
            (profile,),
            max_requirements_per_profile=1,
        )


def test_profile_digest_changes_with_authorized_requirements() -> None:
    original = _profile()
    changed = ProvisioningProfile(
        profile_id=original.profile_id,
        display_name=original.display_name,
        packages=original.packages
        + (
            PackageRequirement(
                package_id="Microsoft.Teams",
                display_name="Microsoft Teams",
            ),
        ),
        directories=original.directories,
    )

    assert profile_digest(original) != profile_digest(changed)


def test_private_references_are_normalized_before_hashing() -> None:
    assert hash_private_reference(
        " Funcionario-123 ",
        "funcionário",
    ) == hash_private_reference("funcionario-123", "funcionário")
    with pytest.raises(ValueError, match="inválido"):
        hash_private_reference("", "funcionário")


def test_preview_payload_contains_hashes_but_not_private_values() -> None:
    profile = _profile()
    preview = EdgeConfigurationPreview(
        device_id="edge_0123456789abcdef0123456789abcdef",
        organization_id="empresa-manaus",
        profile_name=profile.display_name,
        profile_digest=profile_digest(profile),
        employee_reference_hash=hash_private_reference(
            "maria@empresa.test",
            "funcionário",
        ),
        requester_hash=hash_private_reference("ti.operador", "solicitante"),
        plan=_plan(profile),
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
    )

    payload = str(preview.as_payload())

    assert "maria@empresa.test" not in payload
    assert "ti.operador" not in payload
    assert "Google.Chrome" in payload
    assert "token" not in payload.casefold()
