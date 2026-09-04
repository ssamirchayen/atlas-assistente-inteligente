"""Registro, avaliação e comunicação supervisionada de incidentes LGPD."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import re
from threading import RLock
from typing import Callable, Iterable
from uuid import uuid4

from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import PrivacyPrincipal


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")


def _utc(value: datetime, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} deve possuir fuso horário.")
    return value.astimezone(timezone.utc)


def _identifier(label: str, value: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} é inválido.")
    return value


def _identifiers(label: str, values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} não pode conter duplicidades.")
    for value in result:
        _identifier(label, value)
    return result


def business_days_after(start: datetime, days: int) -> datetime:
    """Soma dias úteis de segunda a sexta; feriados exigem calendário externo."""

    current = _utc(start, label="start")
    if not isinstance(days, int) or isinstance(days, bool) or days < 0:
        raise ValueError("days deve ser inteiro não negativo.")
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


class SecurityProperty(StrEnum):
    CONFIDENTIALITY = "confidentiality"
    INTEGRITY = "integrity"
    AVAILABILITY = "availability"
    AUTHENTICITY = "authenticity"


class IncidentStatus(StrEnum):
    REPORTED = "reported"
    CONFIRMED = "confirmed"
    ASSESSED = "assessed"
    COMMUNICATION_PENDING = "communication_pending"
    COMMUNICATION_READY = "communication_ready"
    CLOSED = "closed"


class IncidentRiskConclusion(StrEnum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    INDETERMINATE = "indeterminate"


class CommunicationPlanStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    READY_FOR_MANUAL_SUBMISSION = "ready_for_manual_submission"


class IncidentAuditAction(StrEnum):
    REPORTED = "reported"
    CONFIRMED = "confirmed"
    ASSESSED = "assessed"
    COMMUNICATION_PREPARED = "communication_prepared"
    COMMUNICATION_APPROVED = "communication_approved"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class PersonalDataIncident:
    incident_id: str
    organization_id: str
    detected_at: datetime
    record_ids: tuple[str, ...]
    categories: tuple[DataCategory, ...]
    security_properties: tuple[SecurityProperty, ...]
    status: IncidentStatus = IncidentStatus.REPORTED
    confirmed_at: datetime | None = None
    affected_subject_count: int | None = None
    involves_sensitive_data: bool = False
    involves_vulnerable_group: bool = False
    large_scale: bool = False
    effective_encryption: bool | None = None
    potential_impacts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.incident_id):
            raise ValueError("incident_id é inválido.")
        _identifier("organization_id", self.organization_id)
        object.__setattr__(self, "detected_at", _utc(self.detected_at, label="detected_at"))
        object.__setattr__(self, "record_ids", _identifiers("record_ids", self.record_ids))
        if not self.record_ids:
            raise ValueError("record_ids não pode ser vazio.")
        if not self.categories or any(
            not isinstance(category, DataCategory) for category in self.categories
        ):
            raise TypeError("categories deve conter DataCategory.")
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("categories não pode conter duplicidades.")
        if not self.security_properties or any(
            not isinstance(item, SecurityProperty) for item in self.security_properties
        ):
            raise TypeError("security_properties deve conter SecurityProperty.")
        if len(self.security_properties) != len(set(self.security_properties)):
            raise ValueError("security_properties não pode conter duplicidades.")
        if not isinstance(self.status, IncidentStatus):
            raise TypeError("status deve ser IncidentStatus.")
        if self.confirmed_at is not None:
            confirmed = _utc(self.confirmed_at, label="confirmed_at")
            if confirmed < self.detected_at:
                raise ValueError("confirmed_at não pode anteceder detected_at.")
            object.__setattr__(self, "confirmed_at", confirmed)
        if self.affected_subject_count is not None and (
            not isinstance(self.affected_subject_count, int)
            or isinstance(self.affected_subject_count, bool)
            or self.affected_subject_count < 0
        ):
            raise ValueError("affected_subject_count deve ser inteiro não negativo.")
        object.__setattr__(
            self,
            "potential_impacts",
            _identifiers("potential_impacts", self.potential_impacts),
        )


@dataclass(frozen=True, slots=True)
class IncidentRiskAssessment:
    assessment_id: str
    incident_id: str
    conclusion: IncidentRiskConclusion
    communication_required: bool | None
    requires_human_review: bool
    reason_codes: tuple[str, ...]
    assessed_at: datetime
    authority_due_at: datetime | None
    subjects_due_at: datetime | None


@dataclass(frozen=True, slots=True)
class CommunicationFacts:
    data_nature_documented: bool
    affected_subjects_documented: bool
    security_measures_documented: bool
    risks_documented: bool
    mitigation_documented: bool
    awareness_date_documented: bool
    controller_contact_documented: bool
    delay_reason_documented: bool = False

    def __post_init__(self) -> None:
        for field_name in self.__dataclass_fields__:
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} deve ser booleano.")

    @property
    def complete(self) -> bool:
        return all(
            (
                self.data_nature_documented,
                self.affected_subjects_documented,
                self.security_measures_documented,
                self.risks_documented,
                self.mitigation_documented,
                self.awareness_date_documented,
                self.controller_contact_documented,
            )
        )


@dataclass(frozen=True, slots=True)
class IncidentCommunicationPlan:
    plan_id: str
    incident_id: str
    organization_id: str
    created_at: datetime
    authority_due_at: datetime
    subjects_due_at: datetime
    supplemental_due_at: datetime | None
    preliminary: bool
    facts: CommunicationFacts
    status: CommunicationPlanStatus = CommunicationPlanStatus.PENDING_APPROVAL
    approval_hashes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("plan_id", "incident_id"):
            if not re.fullmatch(r"[a-f0-9]{32}", getattr(self, label)):
                raise ValueError(f"{label} é inválido.")
        _identifier("organization_id", self.organization_id)
        for label in ("created_at", "authority_due_at", "subjects_due_at"):
            object.__setattr__(self, label, _utc(getattr(self, label), label=label))
        if self.supplemental_due_at is not None:
            object.__setattr__(
                self,
                "supplemental_due_at",
                _utc(self.supplemental_due_at, label="supplemental_due_at"),
            )
        if len(self.approval_hashes) != len(set(self.approval_hashes)):
            raise ValueError("approval_hashes não pode conter duplicidades.")
        if any(not _HEX_DIGEST.fullmatch(item) for item in self.approval_hashes):
            raise ValueError("approval_hashes contém valor inválido.")


@dataclass(frozen=True, slots=True)
class IncidentNotificationTask:
    task_id: str
    plan_id: str
    recipient: str
    due_at: datetime
    manual_submission_required: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.task_id):
            raise ValueError("task_id é inválido.")
        if not re.fullmatch(r"[a-f0-9]{32}", self.plan_id):
            raise ValueError("plan_id é inválido.")
        _identifier("recipient", self.recipient)
        object.__setattr__(self, "due_at", _utc(self.due_at, label="due_at"))
        if not isinstance(self.manual_submission_required, bool):
            raise TypeError("manual_submission_required deve ser booleano.")


@dataclass(frozen=True, slots=True)
class IncidentSubmissionReceipt:
    receipt_id: str
    plan_id: str
    incident_id: str
    submitted_at: datetime
    authority_evidence_digest: str
    subjects_evidence_digest: str
    actor_hash: str

    def __post_init__(self) -> None:
        for label in ("receipt_id", "plan_id", "incident_id"):
            if not re.fullmatch(r"[a-f0-9]{32}", getattr(self, label)):
                raise ValueError(f"{label} é inválido.")
        object.__setattr__(
            self,
            "submitted_at",
            _utc(self.submitted_at, label="submitted_at"),
        )
        for label in (
            "authority_evidence_digest",
            "subjects_evidence_digest",
            "actor_hash",
        ):
            if not _HEX_DIGEST.fullmatch(getattr(self, label)):
                raise ValueError(f"{label} é inválido.")


@dataclass(frozen=True, slots=True)
class IncidentAuditEvent:
    event_id: str
    occurred_at: datetime
    incident_id: str
    organization_id: str
    action: IncidentAuditAction
    actor_hash: str | None
    detail: str


class InMemoryIncidentAuditTrail:
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
        self._events: deque[IncidentAuditEvent] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def append(
        self,
        incident: PersonalDataIncident,
        action: IncidentAuditAction,
        *,
        detail: str,
        actor_hash: str | None = None,
    ) -> IncidentAuditEvent:
        _identifier("detail", detail)
        event = IncidentAuditEvent(
            event_id=uuid4().hex,
            occurred_at=_utc(self._clock(), label="clock"),
            incident_id=incident.incident_id,
            organization_id=incident.organization_id,
            action=action,
            actor_hash=actor_hash,
            detail=detail,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(self, *, organization_id: str | None = None) -> tuple[IncidentAuditEvent, ...]:
        with self._lock:
            events = tuple(self._events)
        if organization_id is None:
            return events
        return tuple(item for item in events if item.organization_id == organization_id)


class IncidentResponseService:
    """Prepara decisões e tarefas; nunca envia comunicação automaticamente."""

    CONFIRM_SCOPE = "privacy.incident.confirm"
    NOTIFY_SCOPE = "privacy.incident.notify"

    def __init__(
        self,
        *,
        pseudonymizer: Pseudonymizer,
        audit: InMemoryIncidentAuditTrail,
        max_incidents: int = 1000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(pseudonymizer, Pseudonymizer):
            raise TypeError("pseudonymizer deve ser Pseudonymizer.")
        if not isinstance(audit, InMemoryIncidentAuditTrail):
            raise TypeError("audit deve ser InMemoryIncidentAuditTrail.")
        if not 1 <= max_incidents <= 100_000:
            raise ValueError("max_incidents deve estar entre 1 e 100000.")
        self._pseudonymizer = pseudonymizer
        self._audit = audit
        self._max_incidents = max_incidents
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._incidents: dict[str, PersonalDataIncident] = {}
        self._assessments: dict[str, IncidentRiskAssessment] = {}
        self._plans: dict[str, IncidentCommunicationPlan] = {}
        self._receipts: dict[str, IncidentSubmissionReceipt] = {}
        self._lock = RLock()

    def report(
        self,
        *,
        organization_id: str,
        detected_at: datetime,
        record_ids: Iterable[str],
        categories: Iterable[DataCategory],
        security_properties: Iterable[SecurityProperty],
        affected_subject_count: int | None = None,
        involves_sensitive_data: bool = False,
        involves_vulnerable_group: bool = False,
        large_scale: bool = False,
        effective_encryption: bool | None = None,
        potential_impacts: Iterable[str] = (),
    ) -> PersonalDataIncident:
        incident = PersonalDataIncident(
            incident_id=uuid4().hex,
            organization_id=organization_id,
            detected_at=detected_at,
            record_ids=tuple(record_ids),
            categories=tuple(categories),
            security_properties=tuple(security_properties),
            affected_subject_count=affected_subject_count,
            involves_sensitive_data=involves_sensitive_data,
            involves_vulnerable_group=involves_vulnerable_group,
            large_scale=large_scale,
            effective_encryption=effective_encryption,
            potential_impacts=tuple(potential_impacts),
        )
        with self._lock:
            if len(self._incidents) >= self._max_incidents:
                terminal = next(
                    (
                        key
                        for key, value in self._incidents.items()
                        if value.status is IncidentStatus.CLOSED
                    ),
                    None,
                )
                if terminal is None:
                    raise OverflowError("Capacidade de incidentes atingida.")
                self._incidents.pop(terminal)
            self._incidents[incident.incident_id] = incident
        self._audit.append(incident, IncidentAuditAction.REPORTED, detail="metadata_only")
        return incident

    def get(self, incident_id: str, *, organization_id: str) -> PersonalDataIncident:
        incident = self._get(incident_id)
        if incident.organization_id != organization_id:
            raise PermissionError("O incidente pertence a outra organização.")
        return incident

    def confirm(
        self,
        principal: PrivacyPrincipal,
        incident_id: str,
        *,
        confirmation: str,
    ) -> PersonalDataIncident:
        incident = self._authorize(principal, incident_id, self.CONFIRM_SCOPE)
        if confirmation != f"CONFIRMAR {incident_id}":
            raise PermissionError("A confirmação não corresponde ao incidente.")
        if incident.status is not IncidentStatus.REPORTED:
            return incident
        confirmed = replace(
            incident,
            status=IncidentStatus.CONFIRMED,
            confirmed_at=_utc(self._clock(), label="clock"),
        )
        with self._lock:
            self._incidents[incident_id] = confirmed
        self._audit.append(
            confirmed,
            IncidentAuditAction.CONFIRMED,
            detail="human_confirmed",
            actor_hash=self._actor_hash(principal),
        )
        return confirmed

    def assess(self, incident_id: str, *, organization_id: str) -> IncidentRiskAssessment:
        incident = self.get(incident_id, organization_id=organization_id)
        if incident.confirmed_at is None:
            conclusion = IncidentRiskConclusion.INDETERMINATE
            required = None
            reasons = ("incident_not_confirmed",)
            due = None
        else:
            due = business_days_after(incident.confirmed_at, 3)
            high_risk = (
                incident.involves_sensitive_data
                or incident.involves_vulnerable_group
                or incident.large_scale
                or bool(incident.potential_impacts)
            )
            missing = (
                incident.affected_subject_count is None
                or incident.effective_encryption is None
            )
            if high_risk:
                conclusion = IncidentRiskConclusion.RELEVANT
                required = True
                reasons = self._risk_reasons(incident)
            elif missing:
                conclusion = IncidentRiskConclusion.INDETERMINATE
                required = None
                reasons = ("evidence_incomplete",)
            else:
                conclusion = IncidentRiskConclusion.NOT_RELEVANT
                required = False
                reasons = ("no_relevant_risk_indicator",)
        assessment = IncidentRiskAssessment(
            assessment_id=uuid4().hex,
            incident_id=incident_id,
            conclusion=conclusion,
            communication_required=required,
            requires_human_review=True,
            reason_codes=reasons,
            assessed_at=_utc(self._clock(), label="clock"),
            authority_due_at=due,
            subjects_due_at=due,
        )
        assessed = replace(incident, status=IncidentStatus.ASSESSED)
        with self._lock:
            self._assessments[incident_id] = assessment
            self._incidents[incident_id] = assessed
        self._audit.append(assessed, IncidentAuditAction.ASSESSED, detail=conclusion.value)
        return assessment

    def prepare_communication(
        self,
        incident_id: str,
        *,
        organization_id: str,
        facts: CommunicationFacts,
    ) -> IncidentCommunicationPlan:
        incident = self.get(incident_id, organization_id=organization_id)
        assessment = self._assessments.get(incident_id)
        if assessment is None or assessment.communication_required is not True:
            raise PermissionError("A avaliação não autorizou preparar comunicação.")
        if assessment.authority_due_at is None or assessment.subjects_due_at is None:
            raise RuntimeError("A avaliação não possui prazo calculado.")
        preliminary = not facts.complete
        plan = IncidentCommunicationPlan(
            plan_id=uuid4().hex,
            incident_id=incident_id,
            organization_id=organization_id,
            created_at=_utc(self._clock(), label="clock"),
            authority_due_at=assessment.authority_due_at,
            subjects_due_at=assessment.subjects_due_at,
            supplemental_due_at=(
                business_days_after(self._clock(), 20) if preliminary else None
            ),
            preliminary=preliminary,
            facts=facts,
        )
        pending = replace(incident, status=IncidentStatus.COMMUNICATION_PENDING)
        with self._lock:
            self._plans[plan.plan_id] = plan
            self._incidents[incident_id] = pending
        self._audit.append(
            pending,
            IncidentAuditAction.COMMUNICATION_PREPARED,
            detail="preliminary" if preliminary else "complete",
        )
        return plan

    def approve_communication(
        self,
        principal: PrivacyPrincipal,
        plan_id: str,
        *,
        confirmation: str,
    ) -> IncidentCommunicationPlan:
        plan = self._plan(plan_id)
        incident = self._authorize(principal, plan.incident_id, self.NOTIFY_SCOPE)
        if "privacy-officer" not in principal.roles:
            raise PermissionError("O operador não possui o papel obrigatório.")
        if confirmation != f"APROVAR {plan_id}":
            raise PermissionError("A confirmação não corresponde ao plano.")
        actor_hash = self._actor_hash(principal)
        with self._lock:
            current = self._plans[plan_id]
            if actor_hash in current.approval_hashes:
                return current
            approvals = current.approval_hashes + (actor_hash,)
            status = (
                CommunicationPlanStatus.READY_FOR_MANUAL_SUBMISSION
                if len(approvals) >= 2
                else CommunicationPlanStatus.PENDING_APPROVAL
            )
            updated = replace(current, approval_hashes=approvals, status=status)
            self._plans[plan_id] = updated
            if status is CommunicationPlanStatus.READY_FOR_MANUAL_SUBMISSION:
                self._incidents[incident.incident_id] = replace(
                    incident,
                    status=IncidentStatus.COMMUNICATION_READY,
                )
        self._audit.append(
            incident,
            IncidentAuditAction.COMMUNICATION_APPROVED,
            detail=f"approval_{len(updated.approval_hashes)}",
            actor_hash=actor_hash,
        )
        return updated

    def notification_tasks(
        self,
        plan_id: str,
        *,
        organization_id: str,
    ) -> tuple[IncidentNotificationTask, ...]:
        plan = self._plan(plan_id)
        if plan.organization_id != organization_id:
            raise PermissionError("O plano pertence a outra organização.")
        if plan.status is not CommunicationPlanStatus.READY_FOR_MANUAL_SUBMISSION:
            raise PermissionError("O plano ainda não está pronto.")
        return (
            IncidentNotificationTask(uuid4().hex, plan_id, "anpd", plan.authority_due_at),
            IncidentNotificationTask(
                uuid4().hex,
                plan_id,
                "affected.data_subjects",
                plan.subjects_due_at,
            ),
        )

    def record_manual_submission(
        self,
        principal: PrivacyPrincipal,
        plan_id: str,
        *,
        confirmation: str,
        authority_evidence_digest: str,
        subjects_evidence_digest: str,
    ) -> IncidentSubmissionReceipt:
        plan = self._plan(plan_id)
        incident = self._authorize(principal, plan.incident_id, self.NOTIFY_SCOPE)
        if "privacy-officer" not in principal.roles:
            raise PermissionError("O operador não possui o papel obrigatório.")
        if plan.status is not CommunicationPlanStatus.READY_FOR_MANUAL_SUBMISSION:
            raise PermissionError("O plano ainda não está pronto.")
        if confirmation != f"REGISTRAR {plan_id}":
            raise PermissionError("A confirmação não corresponde ao plano.")
        for label, value in {
            "authority_evidence_digest": authority_evidence_digest,
            "subjects_evidence_digest": subjects_evidence_digest,
        }.items():
            if not _HEX_DIGEST.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        with self._lock:
            existing = self._receipts.get(plan_id)
            if existing is not None:
                return existing
            receipt = IncidentSubmissionReceipt(
                receipt_id=uuid4().hex,
                plan_id=plan_id,
                incident_id=incident.incident_id,
                submitted_at=_utc(self._clock(), label="clock"),
                authority_evidence_digest=authority_evidence_digest,
                subjects_evidence_digest=subjects_evidence_digest,
                actor_hash=self._actor_hash(principal),
            )
            self._receipts[plan_id] = receipt
            self._incidents[incident.incident_id] = replace(
                incident,
                status=IncidentStatus.CLOSED,
            )
        self._audit.append(
            incident,
            IncidentAuditAction.CLOSED,
            detail="manual_evidence_recorded",
            actor_hash=receipt.actor_hash,
        )
        return receipt

    def _authorize(
        self,
        principal: PrivacyPrincipal,
        incident_id: str,
        scope: str,
    ) -> PersonalDataIncident:
        if not isinstance(principal, PrivacyPrincipal):
            raise TypeError("principal deve ser PrivacyPrincipal.")
        incident = self._get(incident_id)
        if principal.organization_id != incident.organization_id:
            raise PermissionError("O operador pertence a outra organização.")
        if scope not in principal.scopes:
            raise PermissionError("O operador não possui o escopo obrigatório.")
        return incident

    def _get(self, incident_id: str) -> PersonalDataIncident:
        if not isinstance(incident_id, str) or not re.fullmatch(r"[a-f0-9]{32}", incident_id):
            raise ValueError("incident_id é inválido.")
        try:
            return self._incidents[incident_id]
        except KeyError as exc:
            raise KeyError("Incidente não encontrado.") from exc

    def _plan(self, plan_id: str) -> IncidentCommunicationPlan:
        if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id):
            raise ValueError("plan_id é inválido.")
        try:
            return self._plans[plan_id]
        except KeyError as exc:
            raise KeyError("Plano não encontrado.") from exc

    def _actor_hash(self, principal: PrivacyPrincipal) -> str:
        pseudonym = self._pseudonymizer.pseudonymize(
            principal.principal_id,
            namespace=f"incident:{principal.organization_id}:actor",
        )
        return hashlib.sha256(pseudonym.encode("ascii")).hexdigest()

    @staticmethod
    def _risk_reasons(incident: PersonalDataIncident) -> tuple[str, ...]:
        reasons = []
        if incident.involves_sensitive_data:
            reasons.append("sensitive_data")
        if incident.involves_vulnerable_group:
            reasons.append("vulnerable_group")
        if incident.large_scale:
            reasons.append("large_scale")
        if incident.potential_impacts:
            reasons.append("potential_harm")
        return tuple(reasons)
