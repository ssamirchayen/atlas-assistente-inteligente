"""Supervised profile planning for Atlas Edge Stage 2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import secrets
from threading import RLock
from typing import Callable, Protocol

from atlas.edge.agent import ITProvisioningAgent
from atlas.edge.profiles import (
    AuthorizedEdgePlan,
    EdgeConfigurationPreview,
    EdgePlanChallenge,
    EmployeeProfileCatalog,
    EmployeeProfileSummary,
    hash_private_reference,
    profile_digest,
)
from atlas.provisioning.models import DeviceInventory, PackageRequirement
from atlas.provisioning.planner import ProvisioningPlanner


class ProfileInventoryCollector(Protocol):
    def capture(
        self,
        packages: tuple[PackageRequirement, ...] = (),
    ) -> DeviceInventory: ...


class EdgeProfileError(ValueError):
    """Safe profile planning failure without exposing private references."""


@dataclass(frozen=True, slots=True)
class _PendingConfiguration:
    challenge: EdgePlanChallenge
    profile_id: str


class EdgeProfileService:
    """Builds and authorizes plans but cannot execute computer changes."""

    def __init__(
        self,
        *,
        agent: ITProvisioningAgent,
        collector: ProfileInventoryCollector,
        planner: ProvisioningPlanner,
        catalog: EmployeeProfileCatalog,
        approval_ttl_seconds: float = 600.0,
        authorization_ttl_seconds: float = 900.0,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
        max_pending: int = 20,
        max_authorized: int = 20,
    ) -> None:
        if approval_ttl_seconds <= 0 or authorization_ttl_seconds <= 0:
            raise ValueError("As validades do plano devem ser positivas.")
        if max_pending <= 0 or max_authorized <= 0:
            raise ValueError("Os limites de autorização devem ser positivos.")
        self._agent = agent
        self._collector = collector
        self._planner = planner
        self._catalog = catalog
        self._approval_ttl = timedelta(seconds=approval_ttl_seconds)
        self._authorization_ttl = timedelta(
            seconds=authorization_ttl_seconds
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (
            lambda: secrets.token_urlsafe(18)
        )
        self._pending: dict[str, _PendingConfiguration] = {}
        self._authorized: dict[str, AuthorizedEdgePlan] = {}
        self._max_pending = max_pending
        self._max_authorized = max_authorized
        self._lock = RLock()

    def list_profiles(self) -> tuple[EmployeeProfileSummary, ...]:
        return self._catalog.list()

    def prepare_configuration(
        self,
        profile_id: str,
        *,
        employee_reference: str,
        requester_id: str,
    ) -> EdgePlanChallenge:
        state = self._require_active_device()
        profile = self._catalog.get(profile_id)
        employee_hash = hash_private_reference(
            employee_reference,
            "A referência do funcionário",
        )
        requester_hash = hash_private_reference(
            requester_id,
            "O solicitante",
        )
        inventory = self._collector.capture(profile.packages)
        plan = self._planner.build(profile, inventory)
        created_at = self._now()
        preview = EdgeConfigurationPreview(
            device_id=state.identity.device_id,
            organization_id=state.enrollment.organization_id,
            profile_name=profile.display_name,
            profile_digest=profile_digest(profile),
            employee_reference_hash=employee_hash,
            requester_hash=requester_hash,
            plan=plan,
            created_at=created_at,
            expires_at=created_at + self._approval_ttl,
        )
        token = self._token_factory().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", token):
            raise EdgeProfileError("O gerador produziu um token inválido.")
        challenge = EdgePlanChallenge(token=token, preview=preview)
        with self._lock:
            self._prune_expired()
            if len(self._pending) >= self._max_pending:
                raise OverflowError("Existem muitos planos aguardando aprovação.")
            self._pending[token] = _PendingConfiguration(
                challenge=challenge,
                profile_id=profile.profile_id,
            )
        return challenge

    def authorize_configuration(
        self,
        token: str,
        *,
        approver_id: str,
    ) -> AuthorizedEdgePlan:
        with self._lock:
            now = self._now()
            self._authorized = {
                identifier: item
                for identifier, item in self._authorized.items()
                if now < item.valid_until
            }
            if len(self._authorized) >= self._max_authorized:
                raise OverflowError(
                    "Existem muitas autorizações aguardando fila."
                )
            pending = self._pending.pop(token, None)
        if pending is None:
            raise EdgeProfileError("O plano não existe ou já foi utilizado.")
        preview = pending.challenge.preview
        now = self._now()
        if now >= preview.expires_at:
            raise EdgeProfileError("A aprovação do plano expirou.")
        approver_hash = hash_private_reference(
            approver_id,
            "O responsável pela aprovação",
        )
        if approver_hash == preview.requester_hash:
            raise PermissionError(
                "O solicitante não pode aprovar o próprio plano."
            )

        state = self._require_active_device()
        if (
            state.identity.device_id != preview.device_id
            or state.enrollment.organization_id != preview.organization_id
        ):
            raise PermissionError("O vínculo do dispositivo mudou.")

        profile = self._catalog.get(pending.profile_id)
        if profile_digest(profile) != preview.profile_digest:
            raise PermissionError(
                "O perfil mudou após a solicitação; gere outro plano."
            )
        inventory = self._collector.capture(profile.packages)
        if inventory.fingerprint() != preview.plan.inventory_fingerprint:
            raise PermissionError(
                "O computador mudou após a solicitação; gere outro plano."
            )

        authorization = AuthorizedEdgePlan(
            preview=preview,
            approver_hash=approver_hash,
            authorized_at=now,
            valid_until=now + self._authorization_ttl,
        )
        with self._lock:
            self._authorized[authorization.authorization_id] = authorization
        return authorization

    def inspect_pending_configuration(self, token: str) -> EdgePlanChallenge:
        """Return a pending challenge for policy validation without consuming it."""

        with self._lock:
            pending = self._pending.get(token)
        if pending is None or self._now() >= pending.challenge.preview.expires_at:
            raise EdgeProfileError("O plano não existe ou está expirado.")
        return pending.challenge

    def inspect_authorized_configuration(
        self,
        authorization_id: str,
    ) -> AuthorizedEdgePlan:
        """Return an authorization for policy validation without consuming it."""

        with self._lock:
            authorization = self._authorized.get(authorization_id)
        if authorization is None or self._now() >= authorization.valid_until:
            raise EdgeProfileError("A autorização não existe ou está expirada.")
        return authorization

    def consume_authorized_configuration(
        self,
        authorization_id: str,
    ) -> AuthorizedEdgePlan:
        """Transfer a trusted authorization once into the local task queue."""

        with self._lock:
            authorization = self._authorized.pop(authorization_id, None)
        if authorization is None:
            raise EdgeProfileError(
                "A autorização não existe ou já foi utilizada."
            )
        if self._now() >= authorization.valid_until:
            raise EdgeProfileError("A autorização de execução expirou.")
        self._require_active_device()
        return authorization

    def revoke_pending_configuration(self, token: str | None = None) -> None:
        with self._lock:
            if token is None:
                self._pending.clear()
            else:
                self._pending.pop(token, None)

    def revoke_authorized_configuration(self, authorization_id: str) -> None:
        with self._lock:
            self._authorized.pop(authorization_id, None)

    def revoke_authorized_configurations(self) -> None:
        with self._lock:
            self._authorized.clear()

    def _require_active_device(self):
        state = self._agent.state
        if state.enrollment is None:
            raise PermissionError("O dispositivo ainda não está cadastrado.")
        if state.paused:
            raise PermissionError("O Atlas Edge está pausado neste dispositivo.")
        return state

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("O relógio do serviço deve possuir fuso horário.")
        return value.astimezone(timezone.utc)

    def _prune_expired(self) -> None:
        now = self._now()
        self._pending = {
            token: item
            for token, item in self._pending.items()
            if now < item.challenge.preview.expires_at
        }
        self._authorized = {
            identifier: item
            for identifier, item in self._authorized.items()
            if now < item.valid_until
        }
