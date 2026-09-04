"""Fluxo supervisionado para o exercício de direitos dos titulares."""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import hmac
import re
import secrets
from threading import RLock
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping
from uuid import uuid4

from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.policy import (
    DataTreatmentRequest,
    PrivacyAction,
    PrivacyPolicyEngine,
    PrivacyPrincipal,
)
from atlas.privacy.subject_data import DeletionPlan, SubjectDataSource


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_PSEUDONYM = re.compile(r"^psn_[a-f0-9]{64}$")


def _utc(value: datetime, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} deve possuir fuso horário.")
    return value.astimezone(timezone.utc)


def _safe_identifiers(
    label: str,
    values: Iterable[str],
    *,
    required: bool = True,
) -> tuple[str, ...]:
    result = tuple(values)
    if required and not result:
        raise ValueError(f"{label} não pode ser vazio.")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} não pode conter duplicidades.")
    if any(not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value) for value in result):
        raise ValueError(f"{label} contém identificador inválido.")
    return result


class SubjectRight(StrEnum):
    CONFIRMATION = "confirmation"
    ACCESS = "access"
    CORRECTION = "correction"
    PORTABILITY = "portability"
    DELETION = "deletion"

    @property
    def mutates_data(self) -> bool:
        return self in {SubjectRight.CORRECTION, SubjectRight.DELETION}

    @property
    def privacy_action(self) -> PrivacyAction:
        return {
            SubjectRight.CONFIRMATION: PrivacyAction.READ,
            SubjectRight.ACCESS: PrivacyAction.READ,
            SubjectRight.CORRECTION: PrivacyAction.UPDATE,
            SubjectRight.PORTABILITY: PrivacyAction.EXPORT,
            SubjectRight.DELETION: PrivacyAction.DELETE,
        }[self]


class RightsResponseMode(StrEnum):
    SIMPLIFIED = "simplified"
    COMPLETE = "complete"


class RightsRequestStatus(StrEnum):
    IDENTITY_PENDING = "identity_pending"
    VERIFIED = "verified"
    APPROVED = "approved"
    DENIED = "denied"
    BLOCKED = "blocked"
    COMPLETED = "completed"

    @property
    def terminal(self) -> bool:
        return self in {
            RightsRequestStatus.DENIED,
            RightsRequestStatus.BLOCKED,
            RightsRequestStatus.COMPLETED,
        }


class RightsDenialReason(StrEnum):
    REQUEST_INVALID = "request_invalid"
    IDENTITY_FAILED = "identity_failed"
    NOT_CONTROLLER = "not_controller"
    POLICY_DENIED = "policy_denied"
    RETENTION_REQUIRED = "retention_required"
    UNSUPPORTED_ATOMIC_MUTATION = "unsupported_atomic_mutation"
    SECURITY_RISK = "security_risk"


class RightsAuditAction(StrEnum):
    SUBMITTED = "submitted"
    CHALLENGE_ISSUED = "challenge_issued"
    IDENTITY_VERIFIED = "identity_verified"
    IDENTITY_FAILED = "identity_failed"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTION_PLANNED = "execution_planned"
    EXECUTION_BLOCKED = "execution_blocked"
    COMPLETED = "completed"


class RightsExecutionOutcome(StrEnum):
    COMPLETED = "completed"
    PLANNED = "planned"
    BLOCKED = "blocked"
    ALREADY_COMPLETED = "already_completed"


@dataclass(frozen=True, slots=True)
class RightsSourceSelection:
    source_id: str
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not _SAFE_IDENTIFIER.fullmatch(
            self.source_id
        ):
            raise ValueError("source_id é inválido.")
        object.__setattr__(self, "fields", _safe_identifiers("fields", self.fields))


@dataclass(frozen=True, slots=True)
class SubjectRightsRequest:
    request_id: str
    organization_id: str
    subject_pseudonym: str
    right: SubjectRight
    response_mode: RightsResponseMode
    selections: tuple[RightsSourceSelection, ...]
    status: RightsRequestStatus
    created_at: datetime
    due_at: datetime | None
    verified_at: datetime | None = None
    approval_hashes: tuple[str, ...] = ()
    denial_reason: RightsDenialReason | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.request_id):
            raise ValueError("request_id é inválido.")
        if not _SAFE_IDENTIFIER.fullmatch(self.organization_id):
            raise ValueError("organization_id é inválido.")
        if not _PSEUDONYM.fullmatch(self.subject_pseudonym):
            raise ValueError("subject_pseudonym é inválido.")
        if not isinstance(self.right, SubjectRight):
            raise TypeError("right deve ser SubjectRight.")
        if not isinstance(self.response_mode, RightsResponseMode):
            raise TypeError("response_mode deve ser RightsResponseMode.")
        if not self.selections or any(
            not isinstance(selection, RightsSourceSelection)
            for selection in self.selections
        ):
            raise TypeError("selections deve conter RightsSourceSelection.")
        source_ids = tuple(selection.source_id for selection in self.selections)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("selections não pode repetir uma fonte.")
        if not isinstance(self.status, RightsRequestStatus):
            raise TypeError("status deve ser RightsRequestStatus.")
        object.__setattr__(self, "created_at", _utc(self.created_at, label="created_at"))
        for label in ("due_at", "verified_at", "completed_at"):
            value = getattr(self, label)
            if value is not None:
                object.__setattr__(self, label, _utc(value, label=label))
        if self.due_at is not None and self.due_at < self.created_at:
            raise ValueError("due_at não pode anteceder created_at.")
        if self.verified_at is not None and self.verified_at < self.created_at:
            raise ValueError("verified_at não pode anteceder created_at.")
        if self.completed_at is not None and self.completed_at < self.created_at:
            raise ValueError("completed_at não pode anteceder created_at.")
        if len(self.approval_hashes) != len(set(self.approval_hashes)):
            raise ValueError("approval_hashes não pode conter duplicidades.")
        if any(not _HEX_DIGEST.fullmatch(value) for value in self.approval_hashes):
            raise ValueError("approval_hashes contém valor inválido.")
        if self.denial_reason is not None and not isinstance(
            self.denial_reason, RightsDenialReason
        ):
            raise TypeError("denial_reason deve ser RightsDenialReason.")

    @property
    def required_approvals(self) -> int:
        return 2 if self.right.mutates_data else 1


@dataclass(frozen=True, slots=True)
class VerificationChallenge:
    challenge_id: str
    request_id: str
    token: str = field(repr=False)
    expires_at: datetime

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.challenge_id):
            raise ValueError("challenge_id é inválido.")
        if not re.fullmatch(r"[a-f0-9]{32}", self.request_id):
            raise ValueError("request_id é inválido.")
        if not isinstance(self.token, str) or not self.token:
            raise ValueError("token não pode ser vazio.")
        object.__setattr__(
            self,
            "expires_at",
            _utc(self.expires_at, label="expires_at"),
        )


@dataclass(frozen=True, slots=True)
class RightsMutationPlan:
    source_id: str
    action: SubjectRight
    record_count: int
    fields: tuple[str, ...]
    retention_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.source_id):
            raise ValueError("source_id é inválido.")
        if self.action not in {SubjectRight.CORRECTION, SubjectRight.DELETION}:
            raise ValueError("O plano deve representar uma mutação.")
        if self.record_count < 0:
            raise ValueError("record_count não pode ser negativo.")
        object.__setattr__(self, "fields", _safe_identifiers("fields", self.fields))
        object.__setattr__(
            self,
            "retention_reasons",
            _safe_identifiers(
                "retention_reasons",
                self.retention_reasons,
                required=False,
            ),
        )


@dataclass(frozen=True, slots=True)
class RightsExecutionResult:
    request_id: str
    outcome: RightsExecutionOutcome
    source_count: int
    payload: Mapping[str, Any] = field(default_factory=dict, repr=False)
    mutation_plans: tuple[RightsMutationPlan, ...] = ()
    reason: str | None = None
    replayed: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.request_id):
            raise ValueError("request_id é inválido.")
        if not isinstance(self.outcome, RightsExecutionOutcome):
            raise TypeError("outcome deve ser RightsExecutionOutcome.")
        if self.source_count < 0:
            raise ValueError("source_count não pode ser negativo.")
        if any(
            not isinstance(plan, RightsMutationPlan)
            for plan in self.mutation_plans
        ):
            raise TypeError("mutation_plans deve conter RightsMutationPlan.")
        if self.reason is not None and not _SAFE_IDENTIFIER.fullmatch(self.reason):
            raise ValueError("reason é inválido.")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed deve ser bool.")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class RightsAuditEvent:
    event_id: str
    occurred_at: datetime
    organization_id: str
    request_id: str
    subject_hash: str
    right: SubjectRight
    action: RightsAuditAction
    actor_hash: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", self.event_id):
            raise ValueError("event_id é inválido.")
        object.__setattr__(
            self,
            "occurred_at",
            _utc(self.occurred_at, label="occurred_at"),
        )
        if not _SAFE_IDENTIFIER.fullmatch(self.organization_id):
            raise ValueError("organization_id é inválido.")
        if not re.fullmatch(r"[a-f0-9]{32}", self.request_id):
            raise ValueError("request_id é inválido.")
        if not _HEX_DIGEST.fullmatch(self.subject_hash):
            raise ValueError("subject_hash é inválido.")
        if not isinstance(self.right, SubjectRight):
            raise TypeError("right deve ser SubjectRight.")
        if not isinstance(self.action, RightsAuditAction):
            raise TypeError("action deve ser RightsAuditAction.")
        if self.actor_hash is not None and not _HEX_DIGEST.fullmatch(self.actor_hash):
            raise ValueError("actor_hash é inválido.")
        if self.detail is not None and not _SAFE_IDENTIFIER.fullmatch(self.detail):
            raise ValueError("detail é inválido.")


class InMemoryRightsAuditTrail:
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
        self._events: deque[RightsAuditEvent] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def append(
        self,
        request: SubjectRightsRequest,
        action: RightsAuditAction,
        *,
        actor_hash: str | None = None,
        detail: str | None = None,
    ) -> RightsAuditEvent:
        event = RightsAuditEvent(
            event_id=uuid4().hex,
            occurred_at=self._clock(),
            organization_id=request.organization_id,
            request_id=request.request_id,
            subject_hash=hashlib.sha256(
                request.subject_pseudonym.encode()
            ).hexdigest(),
            right=request.right,
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
    ) -> tuple[RightsAuditEvent, ...]:
        with self._lock:
            events = tuple(self._events)
        if organization_id is None:
            return events
        return tuple(
            event for event in events if event.organization_id == organization_id
        )


@dataclass(slots=True)
class _ChallengeState:
    challenge_id: str
    token_digest: str
    expires_at: datetime
    attempts: int = 0


class SubjectRightsService:
    """Orquestra identidade, revisão, políticas e execução sem efeitos implícitos."""

    PURPOSE = "fulfill.subject_rights"
    REVIEW_ROLE = "privacy-officer"
    REVIEW_SCOPE = "privacy.rights.review"
    EXECUTE_SCOPE = "privacy.rights.execute"

    def __init__(
        self,
        *,
        policy_engine: PrivacyPolicyEngine,
        pseudonymizer: Pseudonymizer,
        sources: Iterable[SubjectDataSource],
        audit: InMemoryRightsAuditTrail,
        allow_mutations: bool = False,
        max_requests: int = 1000,
        challenge_ttl: timedelta = timedelta(minutes=10),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        source_tuple = tuple(sources)
        if not source_tuple:
            raise ValueError("Ao menos uma fonte de dados deve ser registrada.")
        if any(not isinstance(source, SubjectDataSource) for source in source_tuple):
            raise TypeError("sources deve conter SubjectDataSource.")
        source_ids = tuple(source.source_id for source in source_tuple)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_id não pode ser duplicado.")
        if not isinstance(max_requests, int) or isinstance(max_requests, bool):
            raise TypeError("max_requests deve ser inteiro.")
        if not 1 <= max_requests <= 100_000:
            raise ValueError("max_requests deve estar entre 1 e 100000.")
        if not timedelta(minutes=1) <= challenge_ttl <= timedelta(hours=24):
            raise ValueError("challenge_ttl deve ficar entre 1 minuto e 24 horas.")
        if not isinstance(policy_engine, PrivacyPolicyEngine):
            raise TypeError("policy_engine deve ser PrivacyPolicyEngine.")
        if not isinstance(pseudonymizer, Pseudonymizer):
            raise TypeError("pseudonymizer deve ser Pseudonymizer.")
        if not isinstance(audit, InMemoryRightsAuditTrail):
            raise TypeError("audit deve ser InMemoryRightsAuditTrail.")
        if not isinstance(allow_mutations, bool):
            raise TypeError("allow_mutations deve ser bool.")
        self._policy_engine = policy_engine
        self._pseudonymizer = pseudonymizer
        self._sources = {source.source_id: source for source in source_tuple}
        self._audit = audit
        self._allow_mutations = allow_mutations
        self._max_requests = max_requests
        self._challenge_ttl = challenge_ttl
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._challenge_secret = secrets.token_bytes(32)
        self._requests: OrderedDict[str, SubjectRightsRequest] = OrderedDict()
        self._challenges: dict[str, _ChallengeState] = {}
        self._lock = RLock()

    def subject_pseudonym(self, *, organization_id: str, subject_id: str) -> str:
        return self._pseudonymizer.pseudonymize(
            subject_id,
            namespace=f"rights:{organization_id}:subject",
        )

    def submit(
        self,
        *,
        organization_id: str,
        subject_id: str,
        right: SubjectRight,
        selections: Iterable[RightsSourceSelection],
        response_mode: RightsResponseMode = RightsResponseMode.COMPLETE,
    ) -> SubjectRightsRequest:
        if not isinstance(right, SubjectRight):
            raise TypeError("right deve ser SubjectRight.")
        if not isinstance(response_mode, RightsResponseMode):
            raise TypeError("response_mode deve ser RightsResponseMode.")
        selection_tuple = tuple(selections)
        if not selection_tuple:
            raise ValueError("A solicitação deve selecionar ao menos uma fonte.")
        ids = tuple(selection.source_id for selection in selection_tuple)
        if len(ids) != len(set(ids)):
            raise ValueError("A solicitação não pode repetir uma fonte.")
        for selection in selection_tuple:
            source = self._source(selection.source_id)
            if source.organization_id != organization_id:
                raise PermissionError("A fonte pertence a outra organização.")
            if not set(selection.fields).issubset(source.fields):
                raise ValueError("A seleção contém campos não declarados na fonte.")

        now = _utc(self._clock(), label="clock")
        due_at = self._due_at(now, right, response_mode)
        request = SubjectRightsRequest(
            request_id=uuid4().hex,
            organization_id=organization_id,
            subject_pseudonym=self.subject_pseudonym(
                organization_id=organization_id,
                subject_id=subject_id,
            ),
            right=right,
            response_mode=response_mode,
            selections=selection_tuple,
            status=RightsRequestStatus.IDENTITY_PENDING,
            created_at=now,
            due_at=due_at,
        )
        with self._lock:
            self._make_request_capacity()
            self._requests[request.request_id] = request
        self._audit.append(request, RightsAuditAction.SUBMITTED)
        return request

    def get(
        self,
        request_id: str,
        *,
        organization_id: str,
    ) -> SubjectRightsRequest:
        request = self._get(request_id)
        if request.organization_id != organization_id:
            raise PermissionError("A solicitação pertence a outra organização.")
        return request

    def issue_verification_challenge(
        self,
        request_id: str,
        *,
        organization_id: str,
    ) -> VerificationChallenge:
        request = self.get(request_id, organization_id=organization_id)
        if request.status is not RightsRequestStatus.IDENTITY_PENDING:
            raise ValueError("A solicitação não aguarda verificação de identidade.")
        token = secrets.token_urlsafe(24)
        challenge_id = uuid4().hex
        expires_at = _utc(self._clock(), label="clock") + self._challenge_ttl
        state = _ChallengeState(
            challenge_id=challenge_id,
            token_digest=self._challenge_digest(request_id, token),
            expires_at=expires_at,
        )
        with self._lock:
            self._challenges[request_id] = state
        self._audit.append(request, RightsAuditAction.CHALLENGE_ISSUED)
        return VerificationChallenge(
            challenge_id=challenge_id,
            request_id=request_id,
            token=token,
            expires_at=expires_at,
        )

    def verify_identity(
        self,
        request_id: str,
        *,
        organization_id: str,
        token: str,
    ) -> SubjectRightsRequest:
        request = self.get(request_id, organization_id=organization_id)
        if request.status is not RightsRequestStatus.IDENTITY_PENDING:
            raise ValueError("A solicitação não aguarda verificação de identidade.")
        with self._lock:
            state = self._challenges.get(request_id)
            now = _utc(self._clock(), label="clock")
            if state is None or now >= state.expires_at:
                blocked = self._block(request, RightsDenialReason.IDENTITY_FAILED)
                self._audit.append(
                    blocked,
                    RightsAuditAction.IDENTITY_FAILED,
                    detail=RightsDenialReason.IDENTITY_FAILED.value,
                )
                raise PermissionError("O desafio expirou ou não existe.")
            provided = self._challenge_digest(request_id, token)
            if not hmac.compare_digest(provided, state.token_digest):
                state.attempts += 1
                if state.attempts >= 5:
                    blocked = self._block(
                        request,
                        RightsDenialReason.IDENTITY_FAILED,
                    )
                    self._audit.append(
                        blocked,
                        RightsAuditAction.IDENTITY_FAILED,
                        detail=RightsDenialReason.IDENTITY_FAILED.value,
                    )
                raise PermissionError("O código de verificação é inválido.")
            verified = replace(
                request,
                status=RightsRequestStatus.VERIFIED,
                verified_at=now,
            )
            self._requests[request_id] = verified
            self._challenges.pop(request_id, None)
        self._audit.append(verified, RightsAuditAction.IDENTITY_VERIFIED)
        return verified

    def approve(
        self,
        principal: PrivacyPrincipal,
        request_id: str,
        *,
        confirmation: str,
    ) -> SubjectRightsRequest:
        request = self._request_for_principal(
            principal,
            request_id,
            scope=self.REVIEW_SCOPE,
        )
        if request.status not in {
            RightsRequestStatus.VERIFIED,
            RightsRequestStatus.APPROVED,
        }:
            raise ValueError("A solicitação não pode ser aprovada neste estado.")
        if confirmation != f"APROVAR {request_id}":
            raise PermissionError("A confirmação humana não corresponde ao pedido.")
        actor_hash = self._actor_hash(principal)
        with self._lock:
            current = self._requests[request_id]
            if current.status is RightsRequestStatus.APPROVED:
                return current
            approvals = current.approval_hashes
            if actor_hash in approvals:
                return current
            approvals = approvals + (actor_hash,)
            status = (
                RightsRequestStatus.APPROVED
                if len(approvals) >= current.required_approvals
                else RightsRequestStatus.VERIFIED
            )
            approved = replace(
                current,
                approval_hashes=approvals,
                status=status,
            )
            self._requests[request_id] = approved
        self._audit.append(
            approved,
            RightsAuditAction.APPROVED,
            actor_hash=actor_hash,
            detail=f"approval_{len(approved.approval_hashes)}",
        )
        return approved

    def deny(
        self,
        principal: PrivacyPrincipal,
        request_id: str,
        *,
        reason: RightsDenialReason,
    ) -> SubjectRightsRequest:
        request = self._request_for_principal(
            principal,
            request_id,
            scope=self.REVIEW_SCOPE,
        )
        if request.status not in {
            RightsRequestStatus.VERIFIED,
            RightsRequestStatus.APPROVED,
        }:
            raise ValueError("A solicitação não pode ser negada neste estado.")
        if not isinstance(reason, RightsDenialReason):
            raise TypeError("reason deve ser RightsDenialReason.")
        denied = replace(
            request,
            status=RightsRequestStatus.DENIED,
            denial_reason=reason,
        )
        with self._lock:
            self._requests[request_id] = denied
        self._audit.append(
            denied,
            RightsAuditAction.DENIED,
            actor_hash=self._actor_hash(principal),
            detail=reason.value,
        )
        return denied

    def execute(
        self,
        principal: PrivacyPrincipal,
        request_id: str,
        *,
        confirmation: str,
        corrections: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> RightsExecutionResult:
        request = self._request_for_principal(
            principal,
            request_id,
            scope=self.EXECUTE_SCOPE,
        )
        if request.status is RightsRequestStatus.COMPLETED:
            return RightsExecutionResult(
                request_id=request_id,
                outcome=RightsExecutionOutcome.ALREADY_COMPLETED,
                source_count=len(request.selections),
                replayed=True,
            )
        if request.status is not RightsRequestStatus.APPROVED:
            raise PermissionError("A solicitação ainda não foi aprovada.")
        if confirmation != f"EXECUTAR {request_id}":
            raise PermissionError("A confirmação de execução não corresponde ao pedido.")
        if request.right.mutates_data and self._allow_mutations and len(
            request.selections
        ) > 1:
            return self._blocked_result(
                request,
                principal,
                RightsDenialReason.UNSUPPORTED_ATOMIC_MUTATION,
            )

        source_decisions: list[tuple[RightsSourceSelection, SubjectDataSource, Any]] = []
        for selection in request.selections:
            source = self._source(selection.source_id)
            if source.organization_id != request.organization_id:
                return self._blocked_result(
                    request,
                    principal,
                    RightsDenialReason.NOT_CONTROLLER,
                )
            treatment = DataTreatmentRequest(
                organization_id=request.organization_id,
                record_id=source.record_id,
                purpose=self.PURPOSE,
                action=request.right.privacy_action,
                legal_basis=source.legal_basis,
                categories=source.categories,
                fields=selection.fields,
            )
            decision = self._policy_engine.authorize(principal, treatment)
            if not decision.allowed:
                return self._blocked_result(
                    request,
                    principal,
                    RightsDenialReason.POLICY_DENIED,
                    detail=f"policy_{decision.reason.value}",
                )
            source_decisions.append((selection, source, decision))

        if request.right is SubjectRight.CONFIRMATION:
            payload = {
                source.source_id: source.has_subject(request.subject_pseudonym)
                for _, source, _ in source_decisions
            }
            return self._complete(request, principal, payload=payload)
        if request.right in {SubjectRight.ACCESS, SubjectRight.PORTABILITY}:
            payload: dict[str, Any] = {}
            for selection, source, decision in source_decisions:
                raw = source.read(request.subject_pseudonym, selection.fields)
                minimized = self._policy_engine.minimize(decision, raw)
                payload[source.source_id] = minimized.data
            return self._complete(request, principal, payload=payload)
        if request.right is SubjectRight.CORRECTION:
            return self._execute_correction(
                request,
                principal,
                source_decisions,
                corrections,
            )
        return self._execute_deletion(request, principal, source_decisions)

    def _execute_correction(
        self,
        request: SubjectRightsRequest,
        principal: PrivacyPrincipal,
        source_decisions: list[tuple[RightsSourceSelection, SubjectDataSource, Any]],
        corrections: Mapping[str, Mapping[str, Any]] | None,
    ) -> RightsExecutionResult:
        if corrections is None or not isinstance(corrections, Mapping):
            raise ValueError("Correções são obrigatórias para este direito.")
        plans: list[RightsMutationPlan] = []
        normalized: list[tuple[SubjectDataSource, Mapping[str, Any]]] = []
        for selection, source, _ in source_decisions:
            values = corrections.get(source.source_id)
            if not isinstance(values, Mapping) or not values:
                raise ValueError("Cada fonte deve receber correções explícitas.")
            if set(values) != set(selection.fields):
                raise ValueError("Os campos corrigidos devem coincidir com a seleção.")
            plans.append(
                RightsMutationPlan(
                    source_id=source.source_id,
                    action=SubjectRight.CORRECTION,
                    record_count=int(source.has_subject(request.subject_pseudonym)),
                    fields=selection.fields,
                )
            )
            normalized.append((source, values))
        if not self._allow_mutations:
            return self._planned(request, principal, tuple(plans))
        for source, values in normalized:
            source.correct(request.subject_pseudonym, values)
        return self._complete(
            request,
            principal,
            mutation_plans=tuple(plans),
        )

    def _execute_deletion(
        self,
        request: SubjectRightsRequest,
        principal: PrivacyPrincipal,
        source_decisions: list[tuple[RightsSourceSelection, SubjectDataSource, Any]],
    ) -> RightsExecutionResult:
        deletion_plans: list[DeletionPlan] = [
            source.plan_delete(request.subject_pseudonym)
            for _, source, _ in source_decisions
        ]
        plans = tuple(
            RightsMutationPlan(
                source_id=plan.source_id,
                action=SubjectRight.DELETION,
                record_count=plan.record_count,
                fields=next(
                    selection.fields
                    for selection in request.selections
                    if selection.source_id == plan.source_id
                ),
                retention_reasons=plan.retention_reasons,
            )
            for plan in deletion_plans
        )
        if any(not plan.can_delete for plan in deletion_plans):
            return self._blocked_result(
                request,
                principal,
                RightsDenialReason.RETENTION_REQUIRED,
                mutation_plans=plans,
            )
        if not self._allow_mutations:
            return self._planned(request, principal, plans)
        for _, source, _ in source_decisions:
            source.delete(request.subject_pseudonym)
        return self._complete(request, principal, mutation_plans=plans)

    def _complete(
        self,
        request: SubjectRightsRequest,
        principal: PrivacyPrincipal,
        *,
        payload: Mapping[str, Any] | None = None,
        mutation_plans: tuple[RightsMutationPlan, ...] = (),
    ) -> RightsExecutionResult:
        completed = replace(
            request,
            status=RightsRequestStatus.COMPLETED,
            completed_at=_utc(self._clock(), label="clock"),
        )
        with self._lock:
            self._requests[request.request_id] = completed
        self._audit.append(
            completed,
            RightsAuditAction.COMPLETED,
            actor_hash=self._actor_hash(principal),
        )
        return RightsExecutionResult(
            request_id=request.request_id,
            outcome=RightsExecutionOutcome.COMPLETED,
            source_count=len(request.selections),
            payload=payload or {},
            mutation_plans=mutation_plans,
        )

    def _planned(
        self,
        request: SubjectRightsRequest,
        principal: PrivacyPrincipal,
        plans: tuple[RightsMutationPlan, ...],
    ) -> RightsExecutionResult:
        self._audit.append(
            request,
            RightsAuditAction.EXECUTION_PLANNED,
            actor_hash=self._actor_hash(principal),
            detail="dry_run",
        )
        return RightsExecutionResult(
            request_id=request.request_id,
            outcome=RightsExecutionOutcome.PLANNED,
            source_count=len(request.selections),
            mutation_plans=plans,
            reason="dry_run",
        )

    def _blocked_result(
        self,
        request: SubjectRightsRequest,
        principal: PrivacyPrincipal,
        reason: RightsDenialReason,
        *,
        detail: str | None = None,
        mutation_plans: tuple[RightsMutationPlan, ...] = (),
    ) -> RightsExecutionResult:
        blocked = self._block(request, reason)
        self._audit.append(
            blocked,
            RightsAuditAction.EXECUTION_BLOCKED,
            actor_hash=self._actor_hash(principal),
            detail=detail or reason.value,
        )
        return RightsExecutionResult(
            request_id=request.request_id,
            outcome=RightsExecutionOutcome.BLOCKED,
            source_count=len(request.selections),
            mutation_plans=mutation_plans,
            reason=detail or reason.value,
        )

    def _block(
        self,
        request: SubjectRightsRequest,
        reason: RightsDenialReason,
    ) -> SubjectRightsRequest:
        blocked = replace(
            request,
            status=RightsRequestStatus.BLOCKED,
            denial_reason=reason,
        )
        with self._lock:
            self._requests[request.request_id] = blocked
            self._challenges.pop(request.request_id, None)
        return blocked

    def _request_for_principal(
        self,
        principal: PrivacyPrincipal,
        request_id: str,
        *,
        scope: str,
    ) -> SubjectRightsRequest:
        request = self._get(request_id)
        if principal.organization_id != request.organization_id:
            raise PermissionError("O operador pertence a outra organização.")
        if self.REVIEW_ROLE not in principal.roles:
            raise PermissionError("O operador não possui o papel necessário.")
        if scope not in principal.scopes:
            raise PermissionError("O operador não possui o escopo necessário.")
        return request

    def _actor_hash(self, principal: PrivacyPrincipal) -> str:
        pseudonym = self._pseudonymizer.pseudonymize(
            principal.principal_id,
            namespace=f"rights:{principal.organization_id}:operator",
        )
        return hashlib.sha256(pseudonym.encode()).hexdigest()

    def _challenge_digest(self, request_id: str, token: str) -> str:
        normalized = token.strip() if isinstance(token, str) else ""
        return hmac.new(
            self._challenge_secret,
            f"{request_id}\x00{normalized}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def _get(self, request_id: str) -> SubjectRightsRequest:
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[a-f0-9]{32}", request_id
        ):
            raise ValueError("request_id é inválido.")
        with self._lock:
            try:
                return self._requests[request_id]
            except KeyError as error:
                raise KeyError("Solicitação de titular não encontrada.") from error

    def _source(self, source_id: str) -> SubjectDataSource:
        try:
            return self._sources[source_id]
        except KeyError as error:
            raise KeyError("Fonte de dados não registrada.") from error

    def _make_request_capacity(self) -> None:
        if len(self._requests) < self._max_requests:
            return
        for request_id, request in tuple(self._requests.items()):
            if request.status.terminal:
                self._requests.pop(request_id)
                self._challenges.pop(request_id, None)
                return
        raise OverflowError("O limite de solicitações ativas foi atingido.")

    @staticmethod
    def _due_at(
        now: datetime,
        right: SubjectRight,
        response_mode: RightsResponseMode,
    ) -> datetime | None:
        if right not in {SubjectRight.CONFIRMATION, SubjectRight.ACCESS}:
            return None
        if response_mode is RightsResponseMode.SIMPLIFIED:
            return now
        return now + timedelta(days=15)
