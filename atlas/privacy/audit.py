"""Auditoria em memória de decisões, sem payload ou identificador pessoal bruto."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
from threading import RLock
from typing import Callable
from uuid import uuid4

from atlas.privacy.models import DataCategory


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")


class PrivacyAuditOutcome(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class PrivacyAuditEvent:
    event_id: str
    occurred_at: datetime
    decision_id: str
    organization_id: str
    principal_hash: str
    record_id: str
    purpose: str
    action: str
    outcome: PrivacyAuditOutcome
    reason: str
    categories: tuple[DataCategory, ...]
    requested_field_count: int
    consent_receipt_hash: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.event_id):
            raise ValueError("event_id é inválido.")
        if not re.fullmatch(r"[a-f0-9]{32}", self.decision_id):
            raise ValueError("decision_id é inválido.")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at deve possuir fuso horário.")
        object.__setattr__(
            self,
            "occurred_at",
            self.occurred_at.astimezone(timezone.utc),
        )
        for label, value in {
            "organization_id": self.organization_id,
            "record_id": self.record_id,
            "purpose": self.purpose,
            "action": self.action,
            "reason": self.reason,
        }.items():
            if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        if not _HEX_DIGEST.fullmatch(self.principal_hash):
            raise ValueError("principal_hash é inválido.")
        if not isinstance(self.outcome, PrivacyAuditOutcome):
            raise TypeError("outcome deve ser PrivacyAuditOutcome.")
        if any(not isinstance(category, DataCategory) for category in self.categories):
            raise TypeError("categories deve conter DataCategory.")
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("categories não pode conter duplicidades.")
        if self.requested_field_count < 0:
            raise ValueError("requested_field_count não pode ser negativo.")
        if self.consent_receipt_hash is not None and not _HEX_DIGEST.fullmatch(
            self.consent_receipt_hash
        ):
            raise ValueError("consent_receipt_hash é inválido.")


class InMemoryPrivacyAuditTrail:
    """Trilha bounded e thread-safe; persistência será governada depois."""

    def __init__(
        self,
        *,
        max_events: int = 1000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(max_events, int) or isinstance(max_events, bool):
            raise TypeError("max_events deve ser inteiro.")
        if not 1 <= max_events <= 100_000:
            raise ValueError("max_events deve estar entre 1 e 100000.")
        self._events: deque[PrivacyAuditEvent] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def append(
        self,
        *,
        decision_id: str,
        organization_id: str,
        principal_hash: str,
        record_id: str,
        purpose: str,
        action: str,
        outcome: PrivacyAuditOutcome,
        reason: str,
        categories: tuple[DataCategory, ...],
        requested_field_count: int,
        consent_receipt_hash: str | None = None,
    ) -> PrivacyAuditEvent:
        occurred_at = self._clock()
        if occurred_at.tzinfo is None:
            raise ValueError("O relógio da auditoria deve possuir fuso horário.")
        event = PrivacyAuditEvent(
            event_id=uuid4().hex,
            occurred_at=occurred_at,
            decision_id=decision_id,
            organization_id=organization_id,
            principal_hash=principal_hash,
            record_id=record_id,
            purpose=purpose,
            action=action,
            outcome=outcome,
            reason=reason,
            categories=categories,
            requested_field_count=requested_field_count,
            consent_receipt_hash=consent_receipt_hash,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(
        self,
        *,
        organization_id: str | None = None,
    ) -> tuple[PrivacyAuditEvent, ...]:
        with self._lock:
            events = tuple(self._events)
        if organization_id is None:
            return events
        return tuple(
            event for event in events if event.organization_id == organization_id
        )


def new_decision_id() -> str:
    return uuid4().hex
