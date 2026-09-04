"""Descarte supervisionado, idempotente e verificável de dados pessoais."""

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

from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.policy import PrivacyPrincipal
from atlas.privacy.retention import (
    LifecycleAction,
    RetentionCandidate,
    RetentionDecision,
    RetentionEngine,
    RetentionOutcome,
)
from atlas.privacy.subject_data import SubjectDataSource


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


class DisposalPlanStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    EXPIRED = "expired"


class DisposalOutcome(StrEnum):
    PLANNED = "planned"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    MANUAL_ACTION_REQUIRED = "manual_action_required"
    ALREADY_EXECUTED = "already_executed"


class DisposalAuditAction(StrEnum):
    CREATED = "created"
    APPROVED = "approved"
    EXECUTION_PLANNED = "execution_planned"
    EXECUTED = "executed"
    BLOCKED = "blocked"


class NotificationStatus(StrEnum):
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class DisposalPlan:
    plan_id: str
    organization_id: str
    candidate_id: str
    source_id: str
    record_id: str
    subject_hash: str
    action: LifecycleAction
    rule_id: str
    rule_version: int
    record_count: int
    processor_ids: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    status: DisposalPlanStatus = DisposalPlanStatus.PENDING_APPROVAL
    approval_hashes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.plan_id):
            raise ValueError("plan_id é inválido.")
        for label in (
            "organization_id",
            "candidate_id",
            "source_id",
            "record_id",
            "rule_id",
        ):
            _identifier(label, getattr(self, label))
        if not _HEX_DIGEST.fullmatch(self.subject_hash):
            raise ValueError("subject_hash é inválido.")
        if not isinstance(self.action, LifecycleAction):
            raise TypeError("action deve ser LifecycleAction.")
        if not isinstance(self.rule_version, int) or self.rule_version < 1:
            raise ValueError("rule_version deve ser positiva.")
        if not isinstance(self.record_count, int) or self.record_count < 0:
            raise ValueError("record_count não pode ser negativo.")
        if len(self.processor_ids) != len(set(self.processor_ids)):
            raise ValueError("processor_ids não pode conter duplicidades.")
        for processor_id in self.processor_ids:
            _identifier("processor_id", processor_id)
        object.__setattr__(self, "created_at", _utc(self.created_at, label="created_at"))
        object.__setattr__(self, "expires_at", _utc(self.expires_at, label="expires_at"))
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at deve ser posterior a created_at.")
        if not isinstance(self.status, DisposalPlanStatus):
            raise TypeError("status deve ser DisposalPlanStatus.")
        if len(self.approval_hashes) != len(set(self.approval_hashes)):
            raise ValueError("approval_hashes não pode conter duplicidades.")
        if any(not _HEX_DIGEST.fullmatch(value) for value in self.approval_hashes):
            raise ValueError("approval_hashes contém valor inválido.")

    @property
    def required_approvals(self) -> int:
        return 1 if self.action is LifecycleAction.REVIEW else 2


@dataclass(frozen=True, slots=True)
class DisposalReceipt:
    receipt_id: str
    plan_id: str
    plan_digest: str
    organization_id: str
    source_id: str
    record_id: str
    subject_hash: str
    action: LifecycleAction
    affected_count: int
    executed_at: datetime
    actor_hash: str
    evidence_digest: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.receipt_id):
            raise ValueError("receipt_id é inválido.")
        if not re.fullmatch(r"[a-f0-9]{32}", self.plan_id):
            raise ValueError("plan_id é inválido.")
        for label in ("plan_digest", "subject_hash", "actor_hash", "evidence_digest"):
            if not _HEX_DIGEST.fullmatch(getattr(self, label)):
                raise ValueError(f"{label} é inválido.")
        for label in ("organization_id", "source_id", "record_id"):
            _identifier(label, getattr(self, label))
        if not isinstance(self.action, LifecycleAction):
            raise TypeError("action deve ser LifecycleAction.")
        if self.affected_count < 0:
            raise ValueError("affected_count não pode ser negativo.")
        object.__setattr__(
            self,
            "executed_at",
            _utc(self.executed_at, label="executed_at"),
        )


@dataclass(frozen=True, slots=True)
class ProcessorNotificationTask:
    task_id: str
    plan_id: str
    processor_id: str
    action: LifecycleAction
    status: NotificationStatus = NotificationStatus.PENDING

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.task_id):
            raise ValueError("task_id é inválido.")
        if not re.fullmatch(r"[a-f0-9]{32}", self.plan_id):
            raise ValueError("plan_id é inválido.")
        _identifier("processor_id", self.processor_id)


@dataclass(frozen=True, slots=True)
class DisposalExecutionResult:
    plan_id: str
    outcome: DisposalOutcome
    affected_count: int = 0
    receipt: DisposalReceipt | None = None
    notification_tasks: tuple[ProcessorNotificationTask, ...] = ()
    reason: str | None = None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class DisposalAuditEvent:
    event_id: str
    occurred_at: datetime
    plan_id: str
    organization_id: str
    source_id: str
    record_id: str
    subject_hash: str
    action: DisposalAuditAction
    actor_hash: str | None
    detail: str


class InMemoryDisposalAuditTrail:
    """Auditoria limitada, sem payload, telefone, nome ou valor de campo."""

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
        self._events: deque[DisposalAuditEvent] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def append(
        self,
        plan: DisposalPlan,
        action: DisposalAuditAction,
        *,
        actor_hash: str | None = None,
        detail: str,
    ) -> DisposalAuditEvent:
        if actor_hash is not None and not _HEX_DIGEST.fullmatch(actor_hash):
            raise ValueError("actor_hash é inválido.")
        _identifier("detail", detail)
        event = DisposalAuditEvent(
            event_id=uuid4().hex,
            occurred_at=_utc(self._clock(), label="clock"),
            plan_id=plan.plan_id,
            organization_id=plan.organization_id,
            source_id=plan.source_id,
            record_id=plan.record_id,
            subject_hash=plan.subject_hash,
            action=action,
            actor_hash=actor_hash,
            detail=detail,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(
        self,
        *,
        organization_id: str | None = None,
    ) -> tuple[DisposalAuditEvent, ...]:
        with self._lock:
            values = tuple(self._events)
        if organization_id is None:
            return values
        return tuple(
            event for event in values if event.organization_id == organization_id
        )


@dataclass(slots=True)
class _PlanContext:
    candidate: RetentionCandidate = field(repr=False)
    source: SubjectDataSource = field(repr=False)


class DisposalCoordinator:
    """Executa apenas exclusão lógica suportada pelo adaptador, sob supervisão."""

    APPROVE_SCOPE = "privacy.retention.approve"
    EXECUTE_SCOPE = "privacy.retention.execute"
    REQUIRED_ROLE = "privacy-officer"

    def __init__(
        self,
        *,
        retention_engine: RetentionEngine,
        pseudonymizer: Pseudonymizer,
        sources: Iterable[SubjectDataSource],
        audit: InMemoryDisposalAuditTrail,
        allow_mutations: bool = False,
        plan_ttl: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(retention_engine, RetentionEngine):
            raise TypeError("retention_engine deve ser RetentionEngine.")
        if not isinstance(pseudonymizer, Pseudonymizer):
            raise TypeError("pseudonymizer deve ser Pseudonymizer.")
        if not isinstance(audit, InMemoryDisposalAuditTrail):
            raise TypeError("audit deve ser InMemoryDisposalAuditTrail.")
        if not isinstance(allow_mutations, bool):
            raise TypeError("allow_mutations deve ser booleano.")
        if not isinstance(plan_ttl, timedelta) or not (
            timedelta(seconds=30) <= plan_ttl <= timedelta(hours=1)
        ):
            raise ValueError("plan_ttl deve estar entre 30 segundos e 1 hora.")
        source_tuple = tuple(sources)
        if not source_tuple:
            raise ValueError("sources deve conter ao menos uma fonte.")
        source_ids = tuple(source.source_id for source in source_tuple)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("sources não pode repetir source_id.")
        self._retention_engine = retention_engine
        self._pseudonymizer = pseudonymizer
        self._sources = {source.source_id: source for source in source_tuple}
        self._audit = audit
        self._allow_mutations = allow_mutations
        self._plan_ttl = plan_ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._plans: dict[str, DisposalPlan] = {}
        self._contexts: dict[str, _PlanContext] = {}
        self._results: dict[str, DisposalExecutionResult] = {}
        self._lock = RLock()

    def create_plan(self, candidate: RetentionCandidate) -> DisposalPlan:
        if not isinstance(candidate, RetentionCandidate):
            raise TypeError("candidate deve ser RetentionCandidate.")
        source = self._source(candidate.source_id)
        if (
            source.organization_id != candidate.organization_id
            or source.record_id != candidate.record_id
        ):
            raise PermissionError("A fonte não corresponde ao candidato de retenção.")
        decision = self._retention_engine.evaluate(candidate)
        if not decision.executable:
            raise PermissionError(f"Descarte bloqueado: {decision.reason.value}.")
        deletion = source.plan_delete(candidate.subject_pseudonym)
        if deletion.retention_reasons:
            raise PermissionError("A fonte declarou um impedimento de retenção.")
        rule = self._retention_engine.current_rule(candidate)
        if rule is None or decision.rule_id is None or decision.rule_version is None:
            raise RuntimeError("A decisão executável não possui regra de retenção.")
        now = _utc(self._clock(), label="clock")
        plan = DisposalPlan(
            plan_id=uuid4().hex,
            organization_id=candidate.organization_id,
            candidate_id=candidate.candidate_id,
            source_id=candidate.source_id,
            record_id=candidate.record_id,
            subject_hash=candidate.subject_hash,
            action=decision.action,
            rule_id=decision.rule_id,
            rule_version=decision.rule_version,
            record_count=deletion.record_count,
            processor_ids=rule.processor_ids,
            created_at=now,
            expires_at=now + self._plan_ttl,
        )
        with self._lock:
            self._plans[plan.plan_id] = plan
            self._contexts[plan.plan_id] = _PlanContext(candidate, source)
        self._audit.append(
            plan,
            DisposalAuditAction.CREATED,
            detail="retention_due",
        )
        return plan

    def get(self, plan_id: str, *, organization_id: str) -> DisposalPlan:
        plan = self._get(plan_id)
        if plan.organization_id != organization_id:
            raise PermissionError("O plano pertence a outra organização.")
        return plan

    def approve(
        self,
        principal: PrivacyPrincipal,
        plan_id: str,
        *,
        confirmation: str,
    ) -> DisposalPlan:
        plan = self._authorize(
            principal,
            plan_id,
            scope=self.APPROVE_SCOPE,
        )
        if plan.status not in {
            DisposalPlanStatus.PENDING_APPROVAL,
            DisposalPlanStatus.APPROVED,
        }:
            raise ValueError("O plano não pode ser aprovado neste estado.")
        if confirmation != f"APROVAR {plan_id}":
            raise PermissionError("A confirmação humana não corresponde ao plano.")
        actor_hash = self._actor_hash(principal)
        with self._lock:
            current = self._plans[plan_id]
            if current.status is DisposalPlanStatus.APPROVED:
                return current
            if actor_hash in current.approval_hashes:
                return current
            approvals = current.approval_hashes + (actor_hash,)
            status = (
                DisposalPlanStatus.APPROVED
                if len(approvals) >= current.required_approvals
                else DisposalPlanStatus.PENDING_APPROVAL
            )
            updated = replace(
                current,
                approval_hashes=approvals,
                status=status,
            )
            self._plans[plan_id] = updated
        self._audit.append(
            updated,
            DisposalAuditAction.APPROVED,
            actor_hash=actor_hash,
            detail=f"approval_{len(updated.approval_hashes)}",
        )
        return updated

    def execute(
        self,
        principal: PrivacyPrincipal,
        plan_id: str,
        *,
        confirmation: str,
    ) -> DisposalExecutionResult:
        with self._lock:
            cached = self._results.get(plan_id)
            if cached is not None:
                return replace(
                    cached,
                    outcome=DisposalOutcome.ALREADY_EXECUTED,
                    replayed=True,
                )
            plan = self._authorize(
                principal,
                plan_id,
                scope=self.EXECUTE_SCOPE,
            )
            if plan.status is not DisposalPlanStatus.APPROVED:
                raise PermissionError("O plano ainda não recebeu as aprovações.")
            if confirmation != f"EXECUTAR {plan_id}":
                raise PermissionError("A confirmação não corresponde ao plano.")
            now = _utc(self._clock(), label="clock")
            if now >= plan.expires_at:
                return self._block(plan, detail="plan_expired", expired=True)
            context = self._contexts[plan_id]
            decision = self._retention_engine.evaluate(context.candidate)
            mismatch = self._decision_mismatch(plan, decision)
            if mismatch is not None:
                return self._block(plan, detail=mismatch)
            deletion = context.source.plan_delete(
                context.candidate.subject_pseudonym
            )
            if deletion.retention_reasons:
                return self._block(plan, detail="source_retention_hold")
            actor_hash = self._actor_hash(principal)
            if plan.action is not LifecycleAction.DELETE:
                return self._manual_result(plan, actor_hash=actor_hash)
            if not self._allow_mutations:
                result = DisposalExecutionResult(
                    plan_id=plan_id,
                    outcome=DisposalOutcome.PLANNED,
                    affected_count=deletion.record_count,
                    reason="dry_run",
                )
                self._audit.append(
                    plan,
                    DisposalAuditAction.EXECUTION_PLANNED,
                    actor_hash=actor_hash,
                    detail="dry_run",
                )
                return result
            affected = context.source.delete(context.candidate.subject_pseudonym)
            receipt = self._receipt(plan, affected=affected, actor_hash=actor_hash)
            notifications = tuple(
                ProcessorNotificationTask(
                    task_id=uuid4().hex,
                    plan_id=plan.plan_id,
                    processor_id=processor_id,
                    action=plan.action,
                )
                for processor_id in plan.processor_ids
            )
            executed = replace(plan, status=DisposalPlanStatus.EXECUTED)
            self._plans[plan_id] = executed
            result = DisposalExecutionResult(
                plan_id=plan_id,
                outcome=DisposalOutcome.EXECUTED,
                affected_count=affected,
                receipt=receipt,
                notification_tasks=notifications,
            )
            self._results[plan_id] = result
            self._audit.append(
                executed,
                DisposalAuditAction.EXECUTED,
                actor_hash=actor_hash,
                detail="logical_delete_completed",
            )
            return result

    def _authorize(
        self,
        principal: PrivacyPrincipal,
        plan_id: str,
        *,
        scope: str,
    ) -> DisposalPlan:
        if not isinstance(principal, PrivacyPrincipal):
            raise TypeError("principal deve ser PrivacyPrincipal.")
        plan = self._get(plan_id)
        if principal.organization_id != plan.organization_id:
            raise PermissionError("O operador pertence a outra organização.")
        if self.REQUIRED_ROLE not in principal.roles:
            raise PermissionError("O operador não possui o papel obrigatório.")
        if scope not in principal.scopes:
            raise PermissionError("O operador não possui o escopo obrigatório.")
        return plan

    def _source(self, source_id: str) -> SubjectDataSource:
        _identifier("source_id", source_id)
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError("Fonte não encontrada.") from exc

    def _get(self, plan_id: str) -> DisposalPlan:
        if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id):
            raise ValueError("plan_id é inválido.")
        try:
            return self._plans[plan_id]
        except KeyError as exc:
            raise KeyError("Plano não encontrado.") from exc

    def _actor_hash(self, principal: PrivacyPrincipal) -> str:
        pseudonym = self._pseudonymizer.pseudonymize(
            principal.principal_id,
            namespace=f"disposal:{principal.organization_id}:actor",
        )
        return hashlib.sha256(pseudonym.encode("ascii")).hexdigest()

    @staticmethod
    def _decision_mismatch(
        plan: DisposalPlan,
        decision: RetentionDecision,
    ) -> str | None:
        if decision.outcome is not RetentionOutcome.DUE:
            return f"revalidation_{decision.reason.value}"
        if (
            decision.rule_id != plan.rule_id
            or decision.rule_version != plan.rule_version
            or decision.action is not plan.action
        ):
            return "policy_changed"
        return None

    def _block(
        self,
        plan: DisposalPlan,
        *,
        detail: str,
        expired: bool = False,
    ) -> DisposalExecutionResult:
        _identifier("detail", detail)
        status = DisposalPlanStatus.EXPIRED if expired else DisposalPlanStatus.BLOCKED
        updated = replace(plan, status=status)
        self._plans[plan.plan_id] = updated
        result = DisposalExecutionResult(
            plan_id=plan.plan_id,
            outcome=DisposalOutcome.BLOCKED,
            reason=detail,
        )
        self._audit.append(
            updated,
            DisposalAuditAction.BLOCKED,
            detail=detail,
        )
        return result

    def _manual_result(
        self,
        plan: DisposalPlan,
        *,
        actor_hash: str,
    ) -> DisposalExecutionResult:
        updated = replace(plan, status=DisposalPlanStatus.BLOCKED)
        self._plans[plan.plan_id] = updated
        result = DisposalExecutionResult(
            plan_id=plan.plan_id,
            outcome=DisposalOutcome.MANUAL_ACTION_REQUIRED,
            affected_count=plan.record_count,
            reason=f"adapter_required_{plan.action.value}",
        )
        self._audit.append(
            updated,
            DisposalAuditAction.BLOCKED,
            actor_hash=actor_hash,
            detail="adapter_required",
        )
        return result

    def _receipt(
        self,
        plan: DisposalPlan,
        *,
        affected: int,
        actor_hash: str,
    ) -> DisposalReceipt:
        executed_at = _utc(self._clock(), label="clock")
        plan_digest = hashlib.sha256(
            "|".join(
                (
                    plan.plan_id,
                    plan.organization_id,
                    plan.source_id,
                    plan.record_id,
                    plan.subject_hash,
                    plan.rule_id,
                    str(plan.rule_version),
                    plan.action.value,
                )
            ).encode("utf-8")
        ).hexdigest()
        evidence_digest = hashlib.sha256(
            f"{plan_digest}|{affected}|{executed_at.isoformat()}".encode("utf-8")
        ).hexdigest()
        return DisposalReceipt(
            receipt_id=uuid4().hex,
            plan_id=plan.plan_id,
            plan_digest=plan_digest,
            organization_id=plan.organization_id,
            source_id=plan.source_id,
            record_id=plan.record_id,
            subject_hash=plan.subject_hash,
            action=plan.action,
            affected_count=affected,
            executed_at=executed_at,
            actor_hash=actor_hash,
            evidence_digest=evidence_digest,
        )
