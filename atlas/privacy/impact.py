"""RIPD estruturado e supervisionado, derivado do inventário do Atlas."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
from threading import RLock
from typing import Callable, Iterable
from uuid import uuid4

from atlas.privacy.inventory import ProcessingInventory
from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataNature, DataSubject
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


class ImpactAssessmentStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class ResidualRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImpactAuditAction(StrEnum):
    CREATED = "created"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    REPORT_GENERATED = "report_generated"


@dataclass(frozen=True, slots=True)
class ImpactRiskScenario:
    scenario_id: str
    likelihood: int
    impact: int
    controls: tuple[str, ...]
    residual_likelihood: int
    residual_impact: int

    def __post_init__(self) -> None:
        _identifier("scenario_id", self.scenario_id)
        for label in ("likelihood", "impact", "residual_likelihood", "residual_impact"):
            value = getattr(self, label)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                raise ValueError(f"{label} deve estar entre 1 e 5.")
        object.__setattr__(
            self,
            "controls",
            _identifiers("controls", self.controls, required=True),
        )
        if self.residual_score > self.inherent_score:
            raise ValueError("O risco residual não pode superar o risco inerente.")

    @property
    def inherent_score(self) -> int:
        return self.likelihood * self.impact

    @property
    def residual_score(self) -> int:
        return self.residual_likelihood * self.residual_impact

    @property
    def residual_risk(self) -> ResidualRisk:
        score = self.residual_score
        if score <= 4:
            return ResidualRisk.LOW
        if score <= 9:
            return ResidualRisk.MEDIUM
        if score <= 16:
            return ResidualRisk.HIGH
        return ResidualRisk.CRITICAL


@dataclass(frozen=True, slots=True)
class ImpactAssessment:
    assessment_id: str
    organization_id: str
    purpose_code: str
    record_ids: tuple[str, ...]
    necessity_codes: tuple[str, ...]
    proportionality_codes: tuple[str, ...]
    context_codes: tuple[str, ...]
    safeguards: tuple[str, ...]
    risks: tuple[ImpactRiskScenario, ...]
    created_at: datetime
    status: ImpactAssessmentStatus = ImpactAssessmentStatus.DRAFT
    approval_hashes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.assessment_id):
            raise ValueError("assessment_id é inválido.")
        _identifier("organization_id", self.organization_id)
        _identifier("purpose_code", self.purpose_code)
        for label in (
            "record_ids",
            "necessity_codes",
            "proportionality_codes",
            "context_codes",
            "safeguards",
        ):
            object.__setattr__(
                self,
                label,
                _identifiers(label, getattr(self, label), required=label == "record_ids"),
            )
        if len(self.risks) != len({risk.scenario_id for risk in self.risks}):
            raise ValueError("risks não pode repetir scenario_id.")
        if any(not isinstance(risk, ImpactRiskScenario) for risk in self.risks):
            raise TypeError("risks deve conter ImpactRiskScenario.")
        object.__setattr__(self, "created_at", _utc(self.created_at, label="created_at"))
        if len(self.approval_hashes) != len(set(self.approval_hashes)):
            raise ValueError("approval_hashes não pode conter duplicidades.")
        if any(not _HEX_DIGEST.fullmatch(item) for item in self.approval_hashes):
            raise ValueError("approval_hashes contém valor inválido.")


@dataclass(frozen=True, slots=True)
class ImpactEvaluation:
    assessment_id: str
    evaluated_at: datetime
    record_count: int
    includes_sensitive_processing: bool
    includes_children: bool
    includes_international_transfer: bool
    highest_residual_risk: ResidualRisk | None
    missing_sections: tuple[str, ...]
    unresolved_high_risks: tuple[str, ...]
    ready_for_approval: bool


@dataclass(frozen=True, slots=True)
class ImpactReport:
    report_id: str
    assessment_id: str
    organization_id: str
    generated_at: datetime
    inventory_digest: str
    assessment_digest: str
    record_count: int
    highest_residual_risk: ResidualRisk | None
    approved_by_hashes: tuple[str, ...]
    human_approval_required: bool = True
    legal_conformity_declared: bool = False


@dataclass(frozen=True, slots=True)
class ImpactAuditEvent:
    event_id: str
    occurred_at: datetime
    assessment_id: str
    organization_id: str
    action: ImpactAuditAction
    actor_hash: str | None
    detail: str


class InMemoryImpactAuditTrail:
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
        self._events: deque[ImpactAuditEvent] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def append(
        self,
        assessment: ImpactAssessment,
        action: ImpactAuditAction,
        *,
        detail: str,
        actor_hash: str | None = None,
    ) -> ImpactAuditEvent:
        _identifier("detail", detail)
        event = ImpactAuditEvent(
            event_id=uuid4().hex,
            occurred_at=_utc(self._clock(), label="clock"),
            assessment_id=assessment.assessment_id,
            organization_id=assessment.organization_id,
            action=action,
            actor_hash=actor_hash,
            detail=detail,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(self, *, organization_id: str | None = None) -> tuple[ImpactAuditEvent, ...]:
        with self._lock:
            events = tuple(self._events)
        if organization_id is None:
            return events
        return tuple(item for item in events if item.organization_id == organization_id)


class ImpactAssessmentService:
    """Constrói evidência de RIPD sem substituir a avaliação do controlador."""

    APPROVE_SCOPE = "privacy.ripd.approve"

    def __init__(
        self,
        *,
        inventory: ProcessingInventory,
        pseudonymizer: Pseudonymizer,
        audit: InMemoryImpactAuditTrail,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(inventory, ProcessingInventory):
            raise TypeError("inventory deve ser ProcessingInventory.")
        if not isinstance(pseudonymizer, Pseudonymizer):
            raise TypeError("pseudonymizer deve ser Pseudonymizer.")
        if not isinstance(audit, InMemoryImpactAuditTrail):
            raise TypeError("audit deve ser InMemoryImpactAuditTrail.")
        self._inventory = inventory
        self._pseudonymizer = pseudonymizer
        self._audit = audit
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._assessments: dict[str, ImpactAssessment] = {}
        self._evaluations: dict[str, ImpactEvaluation] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        organization_id: str,
        purpose_code: str,
        record_ids: Iterable[str],
        necessity_codes: Iterable[str] = (),
        proportionality_codes: Iterable[str] = (),
        context_codes: Iterable[str] = (),
        safeguards: Iterable[str] = (),
        risks: Iterable[ImpactRiskScenario] = (),
    ) -> ImpactAssessment:
        record_tuple = tuple(record_ids)
        for record_id in record_tuple:
            self._inventory.get(record_id)
        assessment = ImpactAssessment(
            assessment_id=uuid4().hex,
            organization_id=organization_id,
            purpose_code=purpose_code,
            record_ids=record_tuple,
            necessity_codes=tuple(necessity_codes),
            proportionality_codes=tuple(proportionality_codes),
            context_codes=tuple(context_codes),
            safeguards=tuple(safeguards),
            risks=tuple(risks),
            created_at=_utc(self._clock(), label="clock"),
        )
        with self._lock:
            self._assessments[assessment.assessment_id] = assessment
        self._audit.append(assessment, ImpactAuditAction.CREATED, detail="metadata_only")
        return assessment

    def get(self, assessment_id: str, *, organization_id: str) -> ImpactAssessment:
        assessment = self._get(assessment_id)
        if assessment.organization_id != organization_id:
            raise PermissionError("O RIPD pertence a outra organização.")
        return assessment

    def evaluate(self, assessment_id: str, *, organization_id: str) -> ImpactEvaluation:
        assessment = self.get(assessment_id, organization_id=organization_id)
        records = tuple(self._inventory.get(item) for item in assessment.record_ids)
        missing = []
        for field_name in (
            "necessity_codes",
            "proportionality_codes",
            "context_codes",
            "safeguards",
            "risks",
        ):
            if not getattr(assessment, field_name):
                missing.append(f"missing.{field_name}")
        unresolved = tuple(
            risk.scenario_id
            for risk in assessment.risks
            if risk.residual_risk in {ResidualRisk.HIGH, ResidualRisk.CRITICAL}
        )
        residuals = tuple(risk.residual_risk for risk in assessment.risks)
        order = {
            ResidualRisk.LOW: 1,
            ResidualRisk.MEDIUM: 2,
            ResidualRisk.HIGH: 3,
            ResidualRisk.CRITICAL: 4,
        }
        highest = max(residuals, key=order.get) if residuals else None
        evaluation = ImpactEvaluation(
            assessment_id=assessment_id,
            evaluated_at=_utc(self._clock(), label="clock"),
            record_count=len(records),
            includes_sensitive_processing=any(
                record.nature is DataNature.SENSITIVE_PERSONAL for record in records
            ),
            includes_children=any(
                DataSubject.CHILD_OR_ADOLESCENT in record.subjects for record in records
            ),
            includes_international_transfer=any(
                record.international_transfer for record in records
            ),
            highest_residual_risk=highest,
            missing_sections=tuple(missing),
            unresolved_high_risks=unresolved,
            ready_for_approval=not missing and not unresolved,
        )
        with self._lock:
            self._evaluations[assessment_id] = evaluation
        self._audit.append(
            assessment,
            ImpactAuditAction.EVALUATED,
            detail="ready" if evaluation.ready_for_approval else "incomplete",
        )
        return evaluation

    def approve(
        self,
        principal: PrivacyPrincipal,
        assessment_id: str,
        *,
        confirmation: str,
    ) -> ImpactAssessment:
        self._authorize(principal, assessment_id)
        evaluation = self._evaluations.get(assessment_id)
        if evaluation is None or not evaluation.ready_for_approval:
            raise PermissionError("O RIPD ainda possui lacunas ou riscos altos.")
        if confirmation != f"APROVAR {assessment_id}":
            raise PermissionError("A confirmação não corresponde ao RIPD.")
        actor_hash = self._actor_hash(principal)
        with self._lock:
            current = self._assessments[assessment_id]
            if actor_hash in current.approval_hashes:
                return current
            approvals = current.approval_hashes + (actor_hash,)
            status = (
                ImpactAssessmentStatus.APPROVED
                if len(approvals) >= 2
                else ImpactAssessmentStatus.DRAFT
            )
            updated = replace(current, approval_hashes=approvals, status=status)
            self._assessments[assessment_id] = updated
        self._audit.append(
            updated,
            ImpactAuditAction.APPROVED,
            detail=f"approval_{len(updated.approval_hashes)}",
            actor_hash=actor_hash,
        )
        return updated

    def generate_report(
        self,
        assessment_id: str,
        *,
        organization_id: str,
    ) -> ImpactReport:
        assessment = self.get(assessment_id, organization_id=organization_id)
        if assessment.status is not ImpactAssessmentStatus.APPROVED:
            raise PermissionError("O RIPD ainda não foi aprovado por duas pessoas.")
        evaluation = self._evaluations[assessment_id]
        inventory_payload = [
            {
                "record_id": record.record_id,
                "risk": record.risk_level.value,
                "controls": sorted(record.implemented_controls),
            }
            for record in (self._inventory.get(item) for item in assessment.record_ids)
        ]
        inventory_digest = hashlib.sha256(
            json.dumps(inventory_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        assessment_digest = hashlib.sha256(
            "|".join(
                (
                    assessment.assessment_id,
                    assessment.organization_id,
                    assessment.purpose_code,
                    *assessment.record_ids,
                    *assessment.safeguards,
                    *(risk.scenario_id for risk in assessment.risks),
                )
            ).encode("utf-8")
        ).hexdigest()
        report = ImpactReport(
            report_id=uuid4().hex,
            assessment_id=assessment_id,
            organization_id=organization_id,
            generated_at=_utc(self._clock(), label="clock"),
            inventory_digest=inventory_digest,
            assessment_digest=assessment_digest,
            record_count=evaluation.record_count,
            highest_residual_risk=evaluation.highest_residual_risk,
            approved_by_hashes=assessment.approval_hashes,
        )
        self._audit.append(
            assessment,
            ImpactAuditAction.REPORT_GENERATED,
            detail="approved_snapshot",
        )
        return report

    def _authorize(
        self,
        principal: PrivacyPrincipal,
        assessment_id: str,
    ) -> ImpactAssessment:
        if not isinstance(principal, PrivacyPrincipal):
            raise TypeError("principal deve ser PrivacyPrincipal.")
        assessment = self._get(assessment_id)
        if principal.organization_id != assessment.organization_id:
            raise PermissionError("O operador pertence a outra organização.")
        if "privacy-officer" not in principal.roles:
            raise PermissionError("O operador não possui o papel obrigatório.")
        if self.APPROVE_SCOPE not in principal.scopes:
            raise PermissionError("O operador não possui o escopo obrigatório.")
        return assessment

    def _get(self, assessment_id: str) -> ImpactAssessment:
        if not isinstance(assessment_id, str) or not re.fullmatch(
            r"[a-f0-9]{32}", assessment_id
        ):
            raise ValueError("assessment_id é inválido.")
        try:
            return self._assessments[assessment_id]
        except KeyError as exc:
            raise KeyError("RIPD não encontrado.") from exc

    def _actor_hash(self, principal: PrivacyPrincipal) -> str:
        pseudonym = self._pseudonymizer.pseudonymize(
            principal.principal_id,
            namespace=f"ripd:{principal.organization_id}:actor",
        )
        return hashlib.sha256(pseudonym.encode("ascii")).hexdigest()
