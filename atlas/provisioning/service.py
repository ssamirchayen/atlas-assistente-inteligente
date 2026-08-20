"""Aprovação e aplicação de perfis de computadores corporativos."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from atlas.connectors import (
    ConnectorGuard,
    ConnectorOperation,
    ConnectorPrincipal,
)
from atlas.provisioning.executor import ProvisioningExecutor
from atlas.provisioning.inventory import DeviceInventoryCollector
from atlas.provisioning.models import (
    ProvisioningApproval,
    ProvisioningEvidence,
    ProvisioningPlan,
    ProvisioningProfile,
)
from atlas.provisioning.planner import ProvisioningPlanner


@dataclass(frozen=True, slots=True)
class _PendingPlan:
    operation: ConnectorOperation
    plan: ProvisioningPlan
    profile: ProvisioningProfile


class ProvisioningService:
    """Revalida o inventário entre a aprovação e a execução."""

    def __init__(
        self,
        *,
        guard: ConnectorGuard,
        collector: DeviceInventoryCollector,
        planner: ProvisioningPlanner,
        executor: ProvisioningExecutor,
        profiles: tuple[ProvisioningProfile, ...],
    ) -> None:
        profile_map = {profile.profile_id: profile for profile in profiles}

        if not profile_map:
            raise ValueError("Ao menos um perfil é obrigatório.")
        if len(profile_map) != len(profiles):
            raise ValueError("Os perfis devem possuir IDs únicos.")

        self._guard = guard
        self._collector = collector
        self._planner = planner
        self._executor = executor
        self._profiles = profile_map
        self._pending: dict[str, _PendingPlan] = {}
        self._lock = RLock()

    def list_profiles(self) -> tuple[ProvisioningProfile, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def prepare(
        self,
        profile_id: str,
        principal: ConnectorPrincipal,
    ) -> ProvisioningApproval:
        profile = self._profiles.get(profile_id.strip().lower())

        if profile is None:
            raise ValueError("Perfil de provisionamento não encontrado.")

        inventory = self._collector.capture(profile.packages)
        inventory_operation = ConnectorOperation(
            connector_id="device.provisioning",
            capability="inventory",
            parameters={
                "device_sha256": inventory.device_hash,
                "candidate_packages": len(profile.packages),
            },
        )
        inventory_auth = self._guard.authorize(
            inventory_operation,
            principal,
        )

        if not inventory_auth.allowed:
            raise PermissionError(inventory_auth.reason)

        plan = self._planner.build(profile, inventory)
        operation = ConnectorOperation(
            connector_id="device.provisioning",
            capability="apply_plan",
            parameters={
                "plan_sha256": plan.digest(),
                "inventory_sha256": inventory.fingerprint(),
                "profile_id": profile.profile_id,
                "step_count": len(plan.steps),
                "dry_run": self._executor.dry_run,
            },
            batch_size=len(plan.steps),
            idempotency_key=f"provision:{plan.digest()}",
        )
        authorization = self._guard.authorize(operation, principal)
        summary = (
            f"Aplicar o perfil {profile.display_name} com "
            f"{len(plan.steps)} etapa(s)."
        )

        if not authorization.requires_confirmation:
            return ProvisioningApproval(
                plan=plan,
                summary=summary,
                reason=authorization.reason,
            )

        token = authorization.confirmation_token

        if token is None:
            raise RuntimeError("A política não gerou confirmação.")

        with self._lock:
            self._pending[token] = _PendingPlan(
                operation=operation,
                plan=plan,
                profile=profile,
            )

        return ProvisioningApproval(
            plan=plan,
            summary=summary,
            reason=authorization.reason,
            confirmation_token=token,
            expires_at=authorization.confirmation_expires_at,
        )

    def confirm(
        self,
        confirmation_token: str,
        principal: ConnectorPrincipal,
    ) -> ProvisioningEvidence:
        with self._lock:
            pending = self._pending.get(confirmation_token)

        if pending is None:
            raise ValueError("O plano pendente não existe.")

        current_inventory = self._collector.capture(
            pending.profile.packages
        )

        if (
            current_inventory.fingerprint()
            != pending.plan.inventory_fingerprint
        ):
            raise PermissionError(
                "O computador mudou após a aprovação; gere outro plano."
            )

        authorization = self._guard.authorize(
            pending.operation,
            principal,
            confirmation_token=confirmation_token,
        )

        if not authorization.allowed:
            raise PermissionError(authorization.reason)

        with self._lock:
            self._pending.pop(confirmation_token, None)

        return self._executor.apply(pending.plan, current_inventory)
