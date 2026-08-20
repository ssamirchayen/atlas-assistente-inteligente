from __future__ import annotations

import pytest

from atlas.provisioning import (
    DirectoryRequirement,
    PackageRequirement,
    ProvisioningProfile,
)


def test_profile_is_declarative_and_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="escapar"):
        DirectoryRequirement(
            relative_path="../Windows/System32",
            description="Caminho indevido",
        )


def test_package_requires_exact_identifier_and_known_source() -> None:
    with pytest.raises(ValueError, match="ID"):
        PackageRequirement(
            package_id="Google Chrome && calc.exe",
            display_name="Inválido",
        )

    with pytest.raises(ValueError, match="fonte"):
        PackageRequirement(
            package_id="Google.Chrome",
            display_name="Google Chrome",
            source="site-aleatorio",
        )


def test_profile_rejects_duplicate_requirements() -> None:
    package = PackageRequirement(
        package_id="Google.Chrome",
        display_name="Google Chrome",
    )

    with pytest.raises(ValueError, match="únicos"):
        ProvisioningProfile(
            profile_id="sales",
            display_name="Vendas",
            packages=(package, package),
        )
