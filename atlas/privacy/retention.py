"""Políticas de retenção, carência e bloqueios legais do Atlas."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import re
from threading import RLock
from typing import Callable, Iterable
from uuid import uuid4


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_PSEUDONYM = re.compile(r"^psn_[a-f0-9]{64}$")
_MAX_RETENTION = timedelta(days=36_525)
_MAX_GRACE = timedelta(days=365)


def _utc(value: datetime, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} deve possuir fuso horário.")
    return value.astimezone(timezone.utc)


def _identifier(label: str, value: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} é inválido.")
    return value


def _identifiers(
    label: str,
    values: Iterable[str],
    *,
    required: bool = False,
) -> tuple[str, ...]:
    result = tuple(values)
    if required and not result:
        raise ValueError(f"{label} não pode ser vazio.")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} não pode conter duplicidades.")
    for value in result:
        _identifier(label, value)
    return result


def _subject_hash(subject_pseudonym: str) -> str:
    if not isinstance(subject_pseudonym, str) or not _PSEUDONYM.fullmatch(
        subject_pseudonym
    ):
        raise ValueError("subject_pseudonym é inválido.")
    return hashlib.sha256(subject_pseudonym.encode("ascii")).hexdigest()


class RetentionTrigger(StrEnum):
    CREATED_AT = "created_at"
    LAST_ACTIVITY_AT = "last_activity_at"
    PURPOSE_COMPLETED_AT = "purpose_completed_at"
    CONSENT_REVOKED_AT = "consent_revoked_at"


class LifecycleAction(StrEnum):
    DELETE = "delete"
    ANONYMIZE = "anonymize"
    BLOCK = "block"
    REVIEW = "review"


class RetentionRuleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class RetentionOutcome(StrEnum):
    KEEP = "keep"
    GRACE_PERIOD = "grace_period"
    DUE = "due"
    BLOCKED = "blocked"


class RetentionReason(StrEnum):
    NO_POLICY = "no_policy"
    POLICY_INACTIVE = "policy_inactive"
    MISSING_TRIGGER = "missing_trigger"
    NOT_DUE = "not_due"
    GRACE_PERIOD = "grace_period"
    LEGAL_HOLD = "legal_hold"
    RETENTION_DUE = "retention_due"


@dataclass(frozen=True, slots=True)
class RetentionRule:
    rule_id: str
    organization_id: str
    record_id: str
    status: RetentionRuleStatus
    trigger: RetentionTrigger
    retention_period: timedelta
    action: LifecycleAction
    version: int
    grace_period: timedelta = timedelta(0)
    processor_ids: tuple[str, ...] = ()
    approved_by_hash: str | None = None
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        _identifier("rule_id", self.rule_id)
        _identifier("organization_id", self.organization_id)
        _identifier("record_id", self.record_id)
        if not isinstance(self.status, RetentionRuleStatus):
            raise TypeError("status deve ser RetentionRuleStatus.")
        if not isinstance(self.trigger, RetentionTrigger):
            raise TypeError("trigger deve ser RetentionTrigger.")
        if not isinstance(self.action, LifecycleAction):
            raise TypeError("action deve ser LifecycleAction.")
        if not isinstance(self.version, int) or isinstance(self.version, bool):
            raise TypeError("version deve ser inteiro.")
        if self.version < 1:
            raise ValueError("version deve ser positiva.")
        if not isinstance(self.retention_period, timedelta):
            raise TypeError("retention_period deve ser timedelta.")
        if not timedelta(0) < self.retention_period <= _MAX_RETENTION:
            raise ValueError("retention_period deve estar entre 1 microssegundo e 100 anos.")
        if not isinstance(self.grace_period, timedelta):
            raise TypeError("grace_period deve ser timedelta.")
        if not timedelta(0) <= self.grace_period <= _MAX_GRACE:
            raise ValueError("grace_period deve estar entre zero e 365 dias.")
        object.__setattr__(
            self,
            "processor_ids",
            _identifiers("processor_ids", self.processor_ids),
        )
        if self.approved_by_hash is not None and not _HEX_DIGEST.fullmatch(
            self.approved_by_hash
        ):
            raise ValueError("approved_by_hash é inválido.")
        if self.approved_at is not None:
            object.__setattr__(
                self,
                "approved_at",
                _utc(self.approved_at, label="approved_at"),
            )
        if self.status is RetentionRuleStatus.ACTIVE and (
            self.approved_by_hash is None or self.approved_at is None
        ):
            raise ValueError("Uma regra ativa exige aprovação registrada.")


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    candidate_id: str
    organization_id: str
    source_id: str
    record_id: str
    subject_pseudonym: str = field(repr=False)
    created_at: datetime = field(repr=False)
    last_activity_at: datetime | None = field(default=None, repr=False)
    purpose_completed_at: datetime | None = field(default=None, repr=False)
    consent_revoked_at: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        _identifier("candidate_id", self.candidate_id)
        _identifier("organization_id", self.organization_id)
        _identifier("source_id", self.source_id)
        _identifier("record_id", self.record_id)
        _subject_hash(self.subject_pseudonym)
        object.__setattr__(self, "created_at", _utc(self.created_at, label="created_at"))
        for label in (
            "last_activity_at",
            "purpose_completed_at",
            "consent_revoked_at",
        ):
            value = getattr(self, label)
            if value is not None:
                normalized = _utc(value, label=label)
                if normalized < self.created_at:
                    raise ValueError(f"{label} não pode anteceder created_at.")
                object.__setattr__(self, label, normalized)

    @property
    def subject_hash(self) -> str:
        return _subject_hash(self.subject_pseudonym)

    def timestamp_for(self, trigger: RetentionTrigger) -> datetime | None:
        return {
            RetentionTrigger.CREATED_AT: self.created_at,
            RetentionTrigger.LAST_ACTIVITY_AT: self.last_activity_at,
            RetentionTrigger.PURPOSE_COMPLETED_AT: self.purpose_completed_at,
            RetentionTrigger.CONSENT_REVOKED_AT: self.consent_revoked_at,
        }[trigger]


@dataclass(frozen=True, slots=True)
class LegalHold:
    hold_id: str
    organization_id: str
    record_id: str
    reason_code: str
    approved_by_hash: str
    active_from: datetime
    expires_at: datetime
    subject_hash: str | None = None
    released_at: datetime | None = None
    released_by_hash: str | None = None

    def __post_init__(self) -> None:
        _identifier("hold_id", self.hold_id)
        _identifier("organization_id", self.organization_id)
        _identifier("record_id", self.record_id)
        _identifier("reason_code", self.reason_code)
        if not _HEX_DIGEST.fullmatch(self.approved_by_hash):
            raise ValueError("approved_by_hash é inválido.")
        if self.subject_hash is not None and not _HEX_DIGEST.fullmatch(
            self.subject_hash
        ):
            raise ValueError("subject_hash é inválido.")
        object.__setattr__(
            self,
            "active_from",
            _utc(self.active_from, label="active_from"),
        )
        object.__setattr__(
            self,
            "expires_at",
            _utc(self.expires_at, label="expires_at"),
        )
        if self.expires_at <= self.active_from:
            raise ValueError("expires_at deve ser posterior a active_from.")
        if self.released_at is not None:
            released = _utc(self.released_at, label="released_at")
            if released < self.active_from:
                raise ValueError("released_at não pode anteceder active_from.")
            object.__setattr__(self, "released_at", released)
            if self.released_by_hash is None:
                raise ValueError("A liberação exige released_by_hash.")
        if self.released_by_hash is not None and not _HEX_DIGEST.fullmatch(
            self.released_by_hash
        ):
            raise ValueError("released_by_hash é inválido.")

    def matches(self, candidate: RetentionCandidate, now: datetime) -> bool:
        normalized = _utc(now, label="now")
        if self.released_at is not None:
            return False
        if not self.active_from <= normalized < self.expires_at:
            return False
        if (
            self.organization_id != candidate.organization_id
            or self.record_id != candidate.record_id
        ):
            return False
        return self.subject_hash is None or self.subject_hash == candidate.subject_hash


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    decision_id: str
    candidate_id: str
    organization_id: str
    record_id: str
    outcome: RetentionOutcome
    reason: RetentionReason
    evaluated_at: datetime
    action: LifecycleAction | None = None
    rule_id: str | None = None
    rule_version: int | None = None
    due_at: datetime | None = None
    executable_at: datetime | None = None

    @property
    def executable(self) -> bool:
        return self.outcome is RetentionOutcome.DUE and self.action is not None


class RetentionPolicyRegistry:
    """Registro versionado; impede rollback silencioso de regras."""

    def __init__(self, rules: Iterable[RetentionRule] = ()) -> None:
        self._rules: dict[tuple[str, str], RetentionRule] = {}
        self._lock = RLock()
        for rule in rules:
            self.register(rule)

    def register(self, rule: RetentionRule) -> None:
        if not isinstance(rule, RetentionRule):
            raise TypeError("rule deve ser RetentionRule.")
        key = (rule.organization_id, rule.record_id)
        with self._lock:
            current = self._rules.get(key)
            if current is not None and rule.version <= current.version:
                raise ValueError("A nova regra deve possuir versão superior.")
            self._rules[key] = rule

    def resolve(self, organization_id: str, record_id: str) -> RetentionRule | None:
        _identifier("organization_id", organization_id)
        _identifier("record_id", record_id)
        with self._lock:
            return self._rules.get((organization_id, record_id))


class LegalHoldRegistry:
    """Mantém bloqueios temporários, específicos e sempre expirados."""

    def __init__(self, holds: Iterable[LegalHold] = ()) -> None:
        self._holds: dict[str, LegalHold] = {}
        self._lock = RLock()
        for hold in holds:
            self.add(hold)

    def add(self, hold: LegalHold) -> None:
        if not isinstance(hold, LegalHold):
            raise TypeError("hold deve ser LegalHold.")
        with self._lock:
            if hold.hold_id in self._holds:
                raise ValueError("hold_id já existe.")
            self._holds[hold.hold_id] = hold

    def release(
        self,
        hold_id: str,
        *,
        released_at: datetime,
        released_by_hash: str,
    ) -> LegalHold:
        _identifier("hold_id", hold_id)
        if not _HEX_DIGEST.fullmatch(released_by_hash):
            raise ValueError("released_by_hash é inválido.")
        with self._lock:
            current = self._holds.get(hold_id)
            if current is None:
                raise KeyError("Bloqueio não encontrado.")
            if current.released_at is not None:
                return current
            updated = replace(
                current,
                released_at=released_at,
                released_by_hash=released_by_hash,
            )
            self._holds[hold_id] = updated
            return updated

    def active_for(
        self,
        candidate: RetentionCandidate,
        *,
        now: datetime,
    ) -> tuple[LegalHold, ...]:
        with self._lock:
            values = tuple(self._holds.values())
        return tuple(hold for hold in values if hold.matches(candidate, now))


@dataclass(frozen=True, slots=True)
class RetentionAuditEvent:
    event_id: str
    occurred_at: datetime
    decision_id: str
    organization_id: str
    candidate_id: str
    record_id: str
    source_id: str
    subject_hash: str
    outcome: RetentionOutcome
    reason: RetentionReason
    action: LifecycleAction | None
    rule_id: str | None
    rule_version: int | None


class InMemoryRetentionAuditTrail:
    """Auditoria limitada a metadados; nunca registra valores do titular."""

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
        self._events: deque[RetentionAuditEvent] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def append(
        self,
        candidate: RetentionCandidate,
        decision: RetentionDecision,
    ) -> RetentionAuditEvent:
        event = RetentionAuditEvent(
            event_id=uuid4().hex,
            occurred_at=_utc(self._clock(), label="clock"),
            decision_id=decision.decision_id,
            organization_id=candidate.organization_id,
            candidate_id=candidate.candidate_id,
            record_id=candidate.record_id,
            source_id=candidate.source_id,
            subject_hash=candidate.subject_hash,
            outcome=decision.outcome,
            reason=decision.reason,
            action=decision.action,
            rule_id=decision.rule_id,
            rule_version=decision.rule_version,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(
        self,
        *,
        organization_id: str | None = None,
    ) -> tuple[RetentionAuditEvent, ...]:
        with self._lock:
            values = tuple(self._events)
        if organization_id is None:
            return values
        return tuple(
            event for event in values if event.organization_id == organization_id
        )


class RetentionEngine:
    """Calcula o ciclo de vida sem executar mutações em nenhuma fonte."""

    def __init__(
        self,
        *,
        policies: RetentionPolicyRegistry,
        legal_holds: LegalHoldRegistry,
        audit: InMemoryRetentionAuditTrail,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(policies, RetentionPolicyRegistry):
            raise TypeError("policies deve ser RetentionPolicyRegistry.")
        if not isinstance(legal_holds, LegalHoldRegistry):
            raise TypeError("legal_holds deve ser LegalHoldRegistry.")
        if not isinstance(audit, InMemoryRetentionAuditTrail):
            raise TypeError("audit deve ser InMemoryRetentionAuditTrail.")
        self._policies = policies
        self._legal_holds = legal_holds
        self._audit = audit
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def evaluate(self, candidate: RetentionCandidate) -> RetentionDecision:
        if not isinstance(candidate, RetentionCandidate):
            raise TypeError("candidate deve ser RetentionCandidate.")
        now = _utc(self._clock(), label="clock")
        rule = self._policies.resolve(
            candidate.organization_id,
            candidate.record_id,
        )
        if rule is None:
            return self._decision(
                candidate,
                now=now,
                outcome=RetentionOutcome.BLOCKED,
                reason=RetentionReason.NO_POLICY,
            )
        if rule.status is not RetentionRuleStatus.ACTIVE:
            return self._decision(
                candidate,
                now=now,
                outcome=RetentionOutcome.BLOCKED,
                reason=RetentionReason.POLICY_INACTIVE,
                rule=rule,
            )
        trigger_at = candidate.timestamp_for(rule.trigger)
        if trigger_at is None:
            return self._decision(
                candidate,
                now=now,
                outcome=RetentionOutcome.BLOCKED,
                reason=RetentionReason.MISSING_TRIGGER,
                rule=rule,
            )
        due_at = trigger_at + rule.retention_period
        executable_at = due_at + rule.grace_period
        if now < due_at:
            return self._decision(
                candidate,
                now=now,
                outcome=RetentionOutcome.KEEP,
                reason=RetentionReason.NOT_DUE,
                rule=rule,
                due_at=due_at,
                executable_at=executable_at,
            )
        if now < executable_at:
            return self._decision(
                candidate,
                now=now,
                outcome=RetentionOutcome.GRACE_PERIOD,
                reason=RetentionReason.GRACE_PERIOD,
                rule=rule,
                due_at=due_at,
                executable_at=executable_at,
            )
        if self._legal_holds.active_for(candidate, now=now):
            return self._decision(
                candidate,
                now=now,
                outcome=RetentionOutcome.BLOCKED,
                reason=RetentionReason.LEGAL_HOLD,
                rule=rule,
                due_at=due_at,
                executable_at=executable_at,
            )
        return self._decision(
            candidate,
            now=now,
            outcome=RetentionOutcome.DUE,
            reason=RetentionReason.RETENTION_DUE,
            action=rule.action,
            rule=rule,
            due_at=due_at,
            executable_at=executable_at,
        )

    def current_rule(self, candidate: RetentionCandidate) -> RetentionRule | None:
        return self._policies.resolve(
            candidate.organization_id,
            candidate.record_id,
        )

    def _decision(
        self,
        candidate: RetentionCandidate,
        *,
        now: datetime,
        outcome: RetentionOutcome,
        reason: RetentionReason,
        action: LifecycleAction | None = None,
        rule: RetentionRule | None = None,
        due_at: datetime | None = None,
        executable_at: datetime | None = None,
    ) -> RetentionDecision:
        decision = RetentionDecision(
            decision_id=uuid4().hex,
            candidate_id=candidate.candidate_id,
            organization_id=candidate.organization_id,
            record_id=candidate.record_id,
            outcome=outcome,
            reason=reason,
            evaluated_at=now,
            action=action,
            rule_id=rule.rule_id if rule else None,
            rule_version=rule.version if rule else None,
            due_at=due_at,
            executable_at=executable_at,
        )
        self._audit.append(candidate, decision)
        return decision
