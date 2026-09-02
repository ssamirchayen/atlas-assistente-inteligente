from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

from atlas.edge import (
    EdgeAction,
    EdgeOrganizationPolicy,
    EdgePolicyEngine,
    EdgePrincipal,
    EdgeRole,
    build_edge_policy,
)
from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    ManagedSettingRequirement,
    ManagedSettingType,
    PackageRequirement,
    ProvisioningPlanner,
    ProvisioningProfile,
)


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-secure",
        display_name="Funcionário seguro",
        packages=(PackageRequirement("Google.Chrome", "Chrome"),),
        directories=(DirectoryRequirement("Empresa/Equipe", "Workspace"),),
        settings=(
            ManagedSettingRequirement(
                setting_id="browser-corporate",
                setting_type=ManagedSettingType.BROWSER,
                description="Página corporativa",
                parameters={
                    "browser": "chrome",
                    "homepage": "https://portal.empresa.test",
                },
            ),
        ),
    )


def _plan(profile=None):
    profile = profile or _profile()
    inventory = DeviceInventory(
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        device_hash=sha256(b"governance-device").hexdigest(),
        winget_available=True,
        captured_at=NOW,
    )
    return ProvisioningPlanner().build(profile, inventory)


def _principal(role=EdgeRole.OPERATOR, organization="empresa-manaus"):
    return EdgePrincipal("ti.usuario", organization, role)


def _engine(**policy_changes):
    policy = build_edge_policy("empresa-manaus", (_profile(),))
    policy = replace(policy, **policy_changes)
    return EdgePolicyEngine((policy,))


def test_operator_can_prepare_allowlisted_profile() -> None:
    decision = _engine().decide(
        EdgeAction.PLAN_PREPARE,
        _principal(),
        target_organization_id="empresa-manaus",
        profile_id="employee-secure",
        plan=_plan(),
    )

    assert decision.allowed is True
    assert decision.reason_code == "allowed"


def test_role_cannot_assume_approval_capability() -> None:
    decision = _engine().decide(
        EdgeAction.PLAN_APPROVE,
        _principal(EdgeRole.OPERATOR),
        target_organization_id="empresa-manaus",
    )

    assert decision.allowed is False
    assert decision.reason_code == "role_action_denied"


def test_cross_organization_access_is_denied_before_role_check() -> None:
    decision = _engine().decide(
        EdgeAction.PROFILES_LIST,
        _principal(EdgeRole.ADMIN, "empresa-outra"),
        target_organization_id="empresa-manaus",
    )

    assert decision.reason_code == "cross_organization_denied"


def test_unknown_organization_fails_closed() -> None:
    principal = _principal(organization="empresa-sem-politica")
    decision = EdgePolicyEngine(()).decide(
        EdgeAction.PROFILES_LIST,
        principal,
        target_organization_id=principal.organization_id,
    )

    assert decision.reason_code == "organization_policy_missing"


def test_non_allowlisted_profile_is_denied() -> None:
    decision = _engine().decide(
        EdgeAction.PLAN_PREPARE,
        _principal(),
        target_organization_id="empresa-manaus",
        profile_id="perfil-inventado",
    )

    assert decision.reason_code == "profile_not_allowlisted"


def test_package_must_use_exact_reviewed_id() -> None:
    policy = replace(
        build_edge_policy("empresa-manaus", (_profile(),)),
        allowed_package_ids=frozenset(),
    )
    decision = EdgePolicyEngine((policy,)).decide(
        EdgeAction.PLAN_PREPARE,
        _principal(),
        target_organization_id="empresa-manaus",
        plan=_plan(),
    )

    assert decision.reason_code == "package_not_allowlisted"


def test_managed_setting_must_be_allowlisted() -> None:
    decision = _engine(allowed_setting_ids=frozenset()).decide(
        EdgeAction.PLAN_PREPARE,
        _principal(),
        target_organization_id="empresa-manaus",
        plan=_plan(),
    )

    assert decision.reason_code == "setting_not_allowlisted"


def test_directory_root_must_be_allowlisted() -> None:
    decision = _engine(allowed_directory_roots=frozenset()).decide(
        EdgeAction.PLAN_PREPARE,
        _principal(),
        target_organization_id="empresa-manaus",
        plan=_plan(),
    )

    assert decision.reason_code == "directory_root_not_allowlisted"


def test_protected_directory_segment_is_denied() -> None:
    profile = ProvisioningProfile(
        profile_id="employee-secure",
        display_name="Perfil adulterado",
        directories=(DirectoryRequirement("Empresa/Windows", "Protegida"),),
    )
    policy = EdgeOrganizationPolicy(
        organization_id="empresa-manaus",
        allowed_profile_ids=frozenset({"employee-secure"}),
        allowed_package_ids=frozenset(),
        allowed_setting_ids=frozenset(),
        allowed_setting_types=frozenset(),
        allowed_directory_roots=frozenset({"Empresa"}),
    )
    decision = EdgePolicyEngine((policy,)).decide(
        EdgeAction.PLAN_PREPARE,
        _principal(),
        target_organization_id="empresa-manaus",
        plan=_plan(profile),
    )

    assert decision.reason_code == "protected_path_denied"


def test_plan_step_limit_is_enforced() -> None:
    decision = _engine(max_steps=2).decide(
        EdgeAction.PLAN_PREPARE,
        _principal(),
        target_organization_id="empresa-manaus",
        plan=_plan(),
    )

    assert decision.reason_code == "plan_step_limit_exceeded"


def test_real_execution_requires_explicit_policy_switch() -> None:
    decision = _engine().decide(
        EdgeAction.TASK_EXECUTE,
        _principal(EdgeRole.EXECUTOR),
        target_organization_id="empresa-manaus",
        dry_run=False,
    )

    assert decision.reason_code == "real_execution_disabled"


def test_real_execution_can_be_allowed_only_for_executor_role() -> None:
    decision = _engine(allow_real_execution=True).decide(
        EdgeAction.TASK_EXECUTE,
        _principal(EdgeRole.EXECUTOR),
        target_organization_id="empresa-manaus",
        dry_run=False,
    )

    assert decision.allowed is True


def test_principal_hash_does_not_expose_raw_identifier() -> None:
    principal = EdgePrincipal("nome.sensivel@empresa.test", "empresa-manaus", EdgeRole.AUDITOR)

    assert len(principal.principal_hash) == 64
    assert "nome" not in principal.principal_hash
