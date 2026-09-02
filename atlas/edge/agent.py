"""Supervised ITProvisioningAgent foundation for Sprint 23."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
import secrets
from threading import RLock
from typing import Callable, Protocol
from uuid import uuid4

from atlas.edge.models import (
    DeviceEnrollment,
    DeviceIdentity,
    EdgeHeartbeat,
    EdgePersistentState,
    EnrollmentChallenge,
    normalize_organization_id,
)
from atlas.edge.storage import EdgeStateStore
from atlas.provisioning.models import DeviceInventory, PackageRequirement


class InventoryCollector(Protocol):
    def capture(
        self,
        packages: tuple[PackageRequirement, ...] = (),
    ) -> DeviceInventory: ...


class EnrollmentError(ValueError):
    """Safe enrollment failure without leaking the pending token."""


class ITProvisioningAgent:
    """Local device agent with approval, inventory and heartbeat only.

    Stage 1 intentionally has no package executor, remote transport or arbitrary
    command channel. It creates a random identity, waits for explicit enrollment
    approval and produces sanitized heartbeat objects locally.
    """

    def __init__(
        self,
        *,
        store: EdgeStateStore,
        collector: InventoryCollector,
        enrollment_ttl_seconds: float = 600.0,
        agent_version: str = "0.1.0",
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if enrollment_ttl_seconds <= 0:
            raise ValueError("A validade do cadastro deve ser positiva.")
        if not agent_version.strip():
            raise ValueError("A versão do agente é obrigatória.")

        self._store = store
        self._collector = collector
        self._ttl = timedelta(seconds=enrollment_ttl_seconds)
        self._agent_version = agent_version.strip()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (
            lambda: secrets.token_urlsafe(18)
        )
        self._lock = RLock()
        self._pending: dict[str, EnrollmentChallenge] = {}
        self._state = self._load_or_create_state()

    @property
    def state(self) -> EdgePersistentState:
        with self._lock:
            return self._state

    def prepare_enrollment(self, organization_id: str) -> EnrollmentChallenge:
        organization = normalize_organization_id(organization_id)
        with self._lock:
            if self._state.enrollment is not None:
                raise EnrollmentError("O dispositivo já está cadastrado.")

        inventory = self._collector.capture()
        token = self._token_factory().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", token):
            raise EnrollmentError("O gerador produziu um token inválido.")
        challenge = EnrollmentChallenge(
            token=token,
            device_id=self._state.identity.device_id,
            organization_id=organization,
            inventory_fingerprint=inventory.fingerprint(),
            expires_at=self._now() + self._ttl,
        )
        with self._lock:
            self._pending.clear()
            self._pending[token] = challenge
        return challenge

    def confirm_enrollment(
        self,
        token: str,
        *,
        approver_id: str,
    ) -> EdgePersistentState:
        with self._lock:
            challenge = self._pending.pop(token, None)
        if challenge is None:
            raise EnrollmentError("O cadastro não existe ou já foi utilizado.")
        if self._now() >= challenge.expires_at:
            raise EnrollmentError("O cadastro expirou.")

        approver = str(approver_id).strip().casefold()
        if not approver or len(approver) > 128:
            raise EnrollmentError("O responsável pela aprovação é inválido.")

        inventory = self._collector.capture()
        if inventory.fingerprint() != challenge.inventory_fingerprint:
            raise PermissionError(
                "O inventário mudou após a aprovação; gere outro cadastro."
            )

        enrolled = DeviceEnrollment(
            organization_id=challenge.organization_id,
            inventory_fingerprint=challenge.inventory_fingerprint,
            approver_hash=sha256(approver.encode("utf-8")).hexdigest(),
            enrolled_at=self._now(),
        )
        with self._lock:
            if self._state.enrollment is not None:
                raise EnrollmentError("O dispositivo já está cadastrado.")
            updated = replace(self._state, enrollment=enrolled)
            self._store.save(updated)
            self._state = updated
            return self._state

    def heartbeat(self) -> EdgeHeartbeat:
        with self._lock:
            state = self._state
            if state.enrollment is None:
                raise PermissionError("O dispositivo ainda não está cadastrado.")

            inventory = self._collector.capture()
            captured_at = self._now()
            sequence = state.heartbeat_sequence + 1
            heartbeat = EdgeHeartbeat(
                device_id=state.identity.device_id,
                organization_id=state.enrollment.organization_id,
                sequence=sequence,
                status=state.status,
                agent_version=self._agent_version,
                inventory_fingerprint=inventory.fingerprint(),
                os_name=inventory.os_name,
                os_version=inventory.os_version,
                architecture=inventory.architecture,
                winget_available=inventory.winget_available,
                captured_at=captured_at,
            )
            updated = replace(
                self._state,
                heartbeat_sequence=sequence,
                last_heartbeat_at=captured_at,
            )
            self._store.save(updated)
            self._state = updated
        return heartbeat

    def pause(self) -> EdgePersistentState:
        return self._set_paused(True)

    def resume(self) -> EdgePersistentState:
        return self._set_paused(False)

    def revoke_pending_enrollment(self) -> None:
        with self._lock:
            self._pending.clear()

    def _set_paused(self, paused: bool) -> EdgePersistentState:
        with self._lock:
            if self._state.enrollment is None:
                raise PermissionError("O dispositivo ainda não está cadastrado.")
            if self._state.paused is paused:
                return self._state
            updated = replace(self._state, paused=paused)
            self._store.save(updated)
            self._state = updated
            return self._state

    def _load_or_create_state(self) -> EdgePersistentState:
        state = self._store.load()
        if state is not None:
            return state
        created = EdgePersistentState(
            identity=DeviceIdentity(
                device_id=f"edge_{uuid4().hex}",
                created_at=self._now(),
            )
        )
        self._store.save(created)
        return created

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("O relógio do agente deve possuir fuso horário.")
        return value.astimezone(timezone.utc)
