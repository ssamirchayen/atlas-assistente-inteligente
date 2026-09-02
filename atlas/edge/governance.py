"""Central authorization policy for supervised Atlas Edge operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from types import MappingProxyType
from typing import Iterable, Mapping

from atlas.edge.models import normalize_organization_id
from atlas.edge.profiles import hash_private_reference
from atlas.edge.task_queue import EdgeExecutionTask
from atlas.provisioning.models import (
    ManagedSettingType,
    ProvisioningPlan,
    ProvisioningProfile,
    ProvisioningStepType,
)


_PRINCIPAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{1,127}$")
_SAFE_REASON = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORBIDDEN_PARAMETER_KEYS = frozenset(
    {
        "command",
        "credential",
        "password",
        "powershell",
        "script",
        "secret",
        "shell",
        "token",
    }
)
_DEFAULT_PROTECTED_SEGMENTS = frozenset(
    {
        "$recycle.bin",
        ".git",
        ".venv",
        "atlas",
        "boot",
        "data",
        "logs",
        "program files",
        "program files (x86)",
        "programdata",
        "system volume information",
        "system32",
        "users",
        "windows",
    }
)


class EdgeRole(StrEnum):
    """Corporate roles with deliberately narrow responsibilities."""

    AUDITOR = "auditor"
    OPERATOR = "operator"
    APPROVER = "approver"
    EXECUTOR = "executor"
    ADMIN = "admin"


class EdgeAction(StrEnum):
    PROFILES_LIST = "profiles_list"
    PLAN_PREPARE = "plan_prepare"
    PLAN_APPROVE = "plan_approve"
    TASK_ENQUEUE = "task_enqueue"
    TASK_LIST = "task_list"
    TASK_EXECUTE = "task_execute"
    TASK_CANCEL = "task_cancel"
    AUDIT_READ = "audit_read"
    ONBOARDING_LIST = "onboarding_list"
    ONBOARDING_CANCEL = "onboarding_cancel"
    ONBOARDING_RECONCILE = "onboarding_reconcile"


_ROLE_ACTIONS: Mapping[EdgeRole, frozenset[EdgeAction]] = MappingProxyType(
    {
        EdgeRole.AUDITOR: frozenset(
            {
                EdgeAction.PROFILES_LIST,
                EdgeAction.TASK_LIST,
                EdgeAction.AUDIT_READ,
                EdgeAction.ONBOARDING_LIST,
            }
        ),
        EdgeRole.OPERATOR: frozenset(
            {
                EdgeAction.PROFILES_LIST,
                EdgeAction.PLAN_PREPARE,
                EdgeAction.TASK_ENQUEUE,
                EdgeAction.TASK_LIST,
                EdgeAction.TASK_CANCEL,
                EdgeAction.ONBOARDING_LIST,
                EdgeAction.ONBOARDING_CANCEL,
                EdgeAction.ONBOARDING_RECONCILE,
            }
        ),
        EdgeRole.APPROVER: frozenset(
            {
                EdgeAction.PROFILES_LIST,
                EdgeAction.PLAN_APPROVE,
                EdgeAction.TASK_LIST,
                EdgeAction.ONBOARDING_LIST,
            }
        ),
        EdgeRole.EXECUTOR: frozenset(
            {
                EdgeAction.PROFILES_LIST,
                EdgeAction.TASK_LIST,
                EdgeAction.TASK_EXECUTE,
                EdgeAction.TASK_CANCEL,
                EdgeAction.ONBOARDING_LIST,
                EdgeAction.ONBOARDING_RECONCILE,
            }
        ),
        EdgeRole.ADMIN: frozenset(EdgeAction),
    }
)


@dataclass(frozen=True, slots=True)
class EdgePrincipal:
    """Authenticated actor; its raw identifier is never persisted in audit."""

    principal_id: str
    organization_id: str
    role: EdgeRole

    def __post_init__(self) -> None:
        principal_id = self.principal_id.strip()
        if not _PRINCIPAL_ID.fullmatch(principal_id):
            raise ValueError("O identificador do responsável é inválido.")
        if not isinstance(self.role, EdgeRole):
            raise TypeError("role deve ser EdgeRole.")
        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(
            self,
            "organization_id",
            normalize_organization_id(self.organization_id),
        )

    @property
    def principal_hash(self) -> str:
        return hash_private_reference(self.principal_id, "O responsável")


@dataclass(frozen=True, slots=True)
class EdgeOrganizationPolicy:
    """Reviewed allowlists for one organization, without credentials."""

    organization_id: str
    allowed_profile_ids: frozenset[str]
    allowed_package_ids: frozenset[str]
    allowed_setting_ids: frozenset[str]
    allowed_setting_types: frozenset[ManagedSettingType]
    allowed_directory_roots: frozenset[str]
    max_steps: int = 25
    allow_real_execution: bool = False
    require_distinct_executor: bool = True
    protected_path_segments: frozenset[str] = _DEFAULT_PROTECTED_SEGMENTS

    def __post_init__(self) -> None:
        organization_id = normalize_organization_id(self.organization_id)
        profile_ids = _normalized_set(self.allowed_profile_ids)
        package_ids = frozenset(item.strip() for item in self.allowed_package_ids)
        setting_ids = _normalized_set(self.allowed_setting_ids)
        directory_roots = frozenset(
            item.strip().casefold() for item in self.allowed_directory_roots
        )
        protected = frozenset(
            item.strip().casefold() for item in self.protected_path_segments
        )
        if not profile_ids:
            raise ValueError("A política deve permitir ao menos um perfil.")
        if any(not item for item in package_ids):
            raise ValueError("A allowlist de pacotes contém um item vazio.")
        if any(not isinstance(item, ManagedSettingType) for item in self.allowed_setting_types):
            raise TypeError("Os tipos permitidos devem ser ManagedSettingType.")
        if self.max_steps <= 0 or self.max_steps > 50:
            raise ValueError("O limite de etapas deve ficar entre 1 e 50.")
        if any(not item for item in directory_roots | protected):
            raise ValueError("Os segmentos de caminho não podem ser vazios.")
        object.__setattr__(self, "organization_id", organization_id)
        object.__setattr__(self, "allowed_profile_ids", profile_ids)
        object.__setattr__(self, "allowed_package_ids", package_ids)
        object.__setattr__(self, "allowed_setting_ids", setting_ids)
        object.__setattr__(self, "allowed_setting_types", frozenset(self.allowed_setting_types))
        object.__setattr__(self, "allowed_directory_roots", directory_roots)
        object.__setattr__(self, "protected_path_segments", protected)


@dataclass(frozen=True, slots=True)
class EdgePolicyDecision:
    allowed: bool
    reason_code: str

    def __post_init__(self) -> None:
        if not _SAFE_REASON.fullmatch(self.reason_code):
            raise ValueError("O código da decisão de política é inválido.")


class EdgePolicyDenied(PermissionError):
    """A stable, non-sensitive policy denial."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"A política do Atlas Edge recusou a ação ({reason_code}).")


class EdgePolicyEngine:
    """Fail-closed RBAC, tenancy and recipe validation for Atlas Edge."""

    def __init__(self, policies: Iterable[EdgeOrganizationPolicy]) -> None:
        items = tuple(policies)
        mapped = {item.organization_id: item for item in items}
        if len(mapped) != len(items):
            raise ValueError("Cada organização deve possuir uma única política.")
        self._policies: Mapping[str, EdgeOrganizationPolicy] = MappingProxyType(mapped)

    def decide(
        self,
        action: EdgeAction,
        principal: EdgePrincipal,
        *,
        target_organization_id: str,
        profile_id: str | None = None,
        plan: ProvisioningPlan | None = None,
        task: EdgeExecutionTask | None = None,
        dry_run: bool = True,
    ) -> EdgePolicyDecision:
        if not isinstance(action, EdgeAction):
            raise TypeError("action deve ser EdgeAction.")
        target_org = normalize_organization_id(target_organization_id)
        if principal.organization_id != target_org:
            return _deny("cross_organization_denied")
        policy = self._policies.get(target_org)
        if policy is None:
            return _deny("organization_policy_missing")
        if action not in _ROLE_ACTIONS[principal.role]:
            return _deny("role_action_denied")
        if profile_id is not None and profile_id.strip().casefold() not in policy.allowed_profile_ids:
            return _deny("profile_not_allowlisted")
        if plan is not None:
            reason = _validate_plan(plan, policy)
            if reason is not None:
                return _deny(reason)
        if task is not None:
            if task.organization_id != target_org:
                return _deny("cross_organization_denied")
            reason = _validate_plan(task.plan, policy)
            if reason is not None:
                return _deny(reason)
            if (
                action is EdgeAction.TASK_EXECUTE
                and policy.require_distinct_executor
                and principal.principal_hash == task.approver_hash
            ):
                return _deny("executor_must_differ_from_approver")
        if action is EdgeAction.TASK_EXECUTE and not dry_run:
            if not policy.allow_real_execution:
                return _deny("real_execution_disabled")
            if principal.role not in {EdgeRole.EXECUTOR, EdgeRole.ADMIN}:
                return _deny("real_execution_role_denied")
        return EdgePolicyDecision(True, "allowed")

    def require(self, *args, **kwargs) -> EdgePolicyDecision:
        decision = self.decide(*args, **kwargs)
        if not decision.allowed:
            raise EdgePolicyDenied(decision.reason_code)
        return decision


def build_edge_policy(
    organization_id: str,
    profiles: Iterable[ProvisioningProfile],
    *,
    max_steps: int = 25,
    allow_real_execution: bool = False,
    require_distinct_executor: bool = True,
) -> EdgeOrganizationPolicy:
    """Derive exact allowlists from profiles reviewed by corporate IT."""

    items = tuple(profiles)
    if not items:
        raise ValueError("Não existem perfis para compor a política.")
    return EdgeOrganizationPolicy(
        organization_id=organization_id,
        allowed_profile_ids=frozenset(item.profile_id for item in items),
        allowed_package_ids=frozenset(
            package.package_id for profile in items for package in profile.packages
        ),
        allowed_setting_ids=frozenset(
            setting.setting_id for profile in items for setting in profile.settings
        ),
        allowed_setting_types=frozenset(
            setting.setting_type for profile in items for setting in profile.settings
        ),
        allowed_directory_roots=frozenset(
            directory.relative_path.split("/", 1)[0]
            for profile in items
            for directory in profile.directories
        ),
        max_steps=max_steps,
        allow_real_execution=allow_real_execution,
        require_distinct_executor=require_distinct_executor,
    )


def _validate_plan(
    plan: ProvisioningPlan,
    policy: EdgeOrganizationPolicy,
) -> str | None:
    if plan.profile_id not in policy.allowed_profile_ids:
        return "profile_not_allowlisted"
    if len(plan.steps) > policy.max_steps:
        return "plan_step_limit_exceeded"
    setting_types = {
        ProvisioningStepType.CONFIGURE_BROWSER: ManagedSettingType.BROWSER,
        ProvisioningStepType.CONNECT_PRINTER: ManagedSettingType.PRINTER,
        ProvisioningStepType.CONFIGURE_VPN: ManagedSettingType.VPN,
        ProvisioningStepType.CONFIGURE_NETWORK: ManagedSettingType.NETWORK,
    }
    for step in plan.steps:
        keys = {key.casefold() for key in step.parameters}
        if keys & _FORBIDDEN_PARAMETER_KEYS:
            return "free_form_command_denied"
        if step.step_type is ProvisioningStepType.INSTALL_WINGET_PACKAGE:
            if step.parameters.get("package_id") not in policy.allowed_package_ids:
                return "package_not_allowlisted"
        elif step.step_type is ProvisioningStepType.CREATE_DIRECTORY:
            path = step.parameters.get("relative_path", "")
            segments = tuple(part.casefold() for part in path.replace("\\", "/").split("/") if part)
            if not segments or any(item in policy.protected_path_segments for item in segments):
                return "protected_path_denied"
            if segments[0] not in policy.allowed_directory_roots:
                return "directory_root_not_allowlisted"
        else:
            setting_type = setting_types.get(step.step_type)
            if setting_type is None or setting_type not in policy.allowed_setting_types:
                return "setting_type_not_allowlisted"
            if step.parameters.get("setting_id", "").casefold() not in policy.allowed_setting_ids:
                return "setting_not_allowlisted"
    return None


def _deny(reason_code: str) -> EdgePolicyDecision:
    return EdgePolicyDecision(False, reason_code)


def _normalized_set(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(item).strip().casefold() for item in values)
