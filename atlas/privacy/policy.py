"""Motor central de autorização para tratamentos de dados do Atlas."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import re
from threading import RLock
from typing import Callable, Iterable, Mapping, Any

from atlas.privacy.audit import (
    InMemoryPrivacyAuditTrail,
    PrivacyAuditOutcome,
    new_decision_id,
)
from atlas.privacy.consent import ConsentRegistry
from atlas.privacy.inventory import ProcessingInventory
from atlas.privacy.minimization import DataMinimizationResult, DataMinimizer
from atlas.privacy.models import DataCategory, DataNature, DataSubject


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_SAFE_ROLE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")


def _safe_tuple(
    label: str,
    values: Iterable[str],
    *,
    pattern: re.Pattern[str] = _SAFE_IDENTIFIER,
    required: bool = True,
) -> tuple[str, ...]:
    result = tuple(values)
    if required and not result:
        raise ValueError(f"{label} não pode ser vazio.")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} não pode conter duplicidades.")
    if any(not isinstance(value, str) or not pattern.fullmatch(value) for value in result):
        raise ValueError(f"{label} contém um identificador inválido.")
    return result


def _enum_tuple(label: str, values: Iterable[Any], enum_type: type) -> tuple[Any, ...]:
    result = tuple(values)
    if not result:
        raise ValueError(f"{label} não pode ser vazio.")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} não pode conter duplicidades.")
    if any(not isinstance(value, enum_type) for value in result):
        raise TypeError(f"{label} contém tipo inválido.")
    return result


class PrivacyAction(StrEnum):
    COLLECT = "collect"
    READ = "read"
    USE = "use"
    UPDATE = "update"
    SHARE = "share"
    EXPORT = "export"
    DELETE = "delete"


class PolicyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class DeclaredLegalBasis(StrEnum):
    """Hipóteses declaradas pelo controlador; o motor nunca as escolhe."""

    CONSENT = "personal.consent"
    LEGAL_OBLIGATION = "personal.legal_obligation"
    PUBLIC_POLICY = "personal.public_policy"
    CONTRACT = "personal.contract"
    LEGAL_CLAIMS = "personal.legal_claims"
    LIFE_PROTECTION = "personal.life_protection"
    HEALTH_PROTECTION = "personal.health_protection"
    LEGITIMATE_INTEREST = "personal.legitimate_interest"
    CREDIT_PROTECTION = "personal.credit_protection"
    SENSITIVE_SPECIFIC_CONSENT = "sensitive.specific_consent"
    SENSITIVE_LEGAL_OBLIGATION = "sensitive.legal_obligation"
    SENSITIVE_PUBLIC_POLICY = "sensitive.public_policy"
    SENSITIVE_RESEARCH = "sensitive.research"
    SENSITIVE_LEGAL_CLAIMS = "sensitive.legal_claims"
    SENSITIVE_LIFE_PROTECTION = "sensitive.life_protection"
    SENSITIVE_HEALTH_PROTECTION = "sensitive.health_protection"
    SENSITIVE_FRAUD_PREVENTION = "sensitive.fraud_prevention"

    @property
    def requires_consent_receipt(self) -> bool:
        return self in {
            DeclaredLegalBasis.CONSENT,
            DeclaredLegalBasis.SENSITIVE_SPECIFIC_CONSENT,
        }


class PrivacyDecisionReason(StrEnum):
    ALLOWED = "allowed"
    ORGANIZATION_MISMATCH = "organization_mismatch"
    TREATMENT_NOT_INVENTORIED = "treatment_not_inventoried"
    POLICY_NOT_FOUND = "policy_not_found"
    POLICY_NOT_ACTIVE = "policy_not_active"
    ACTION_NOT_ALLOWED = "action_not_allowed"
    ROLE_NOT_ALLOWED = "role_not_allowed"
    SCOPE_MISSING = "scope_missing"
    LEGAL_BASIS_NOT_ALLOWED = "legal_basis_not_allowed"
    CATEGORY_NOT_INVENTORIED = "category_not_inventoried"
    CATEGORY_NOT_ALLOWED = "category_not_allowed"
    FIELD_NOT_ALLOWED = "field_not_allowed"
    SENSITIVE_PROCESSING_DENIED = "sensitive_processing_denied"
    CHILD_DATA_DENIED = "child_data_denied"
    INTERNATIONAL_TRANSFER_DENIED = "international_transfer_denied"
    SUBJECT_REQUIRED = "subject_required"
    CONSENT_MISSING_OR_INVALID = "consent_missing_or_invalid"


@dataclass(frozen=True, slots=True)
class PrivacyPrincipal:
    principal_id: str
    organization_id: str
    roles: tuple[str, ...]
    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        for label, value in {
            "principal_id": self.principal_id,
            "organization_id": self.organization_id,
        }.items():
            if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        object.__setattr__(
            self,
            "roles",
            _safe_tuple("roles", self.roles, pattern=_SAFE_ROLE),
        )
        object.__setattr__(self, "scopes", _safe_tuple("scopes", self.scopes))


@dataclass(frozen=True, slots=True)
class DataTreatmentRequest:
    organization_id: str
    record_id: str
    purpose: str
    action: PrivacyAction
    legal_basis: DeclaredLegalBasis
    categories: tuple[DataCategory, ...]
    fields: tuple[str, ...]
    subject_id: str | None = field(default=None, repr=False)
    consent_receipt_id: str | None = field(default=None, repr=False)
    involves_child: bool = False
    international_transfer: bool = False

    def __post_init__(self) -> None:
        for label, value in {
            "organization_id": self.organization_id,
            "record_id": self.record_id,
            "purpose": self.purpose,
        }.items():
            if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        if not isinstance(self.action, PrivacyAction):
            raise TypeError("action deve ser PrivacyAction.")
        if not isinstance(self.legal_basis, DeclaredLegalBasis):
            raise TypeError("legal_basis deve ser DeclaredLegalBasis.")
        object.__setattr__(
            self,
            "categories",
            _enum_tuple("categories", self.categories, DataCategory),
        )
        object.__setattr__(self, "fields", _safe_tuple("fields", self.fields))
        if self.subject_id is not None and not self.subject_id.strip():
            raise ValueError("subject_id não pode ser vazio.")
        if self.consent_receipt_id is not None and not re.fullmatch(
            r"[a-f0-9]{32}", self.consent_receipt_id
        ):
            raise ValueError("consent_receipt_id é inválido.")


@dataclass(frozen=True, slots=True)
class PrivacyPolicy:
    policy_id: str
    organization_id: str
    record_id: str
    purpose: str
    status: PolicyStatus
    allowed_actions: tuple[PrivacyAction, ...]
    allowed_roles: tuple[str, ...]
    required_scopes: tuple[str, ...]
    allowed_legal_bases: tuple[DeclaredLegalBasis, ...]
    allowed_categories: tuple[DataCategory, ...]
    allowed_fields: tuple[str, ...]
    approved_by_hash: str | None = None
    approved_at: datetime | None = None
    masked_fields: tuple[str, ...] = ()
    pseudonymized_fields: tuple[str, ...] = ()
    allow_sensitive_processing: bool = False
    allow_child_data: bool = False
    allow_international_transfer: bool = False

    def __post_init__(self) -> None:
        for label, value in {
            "policy_id": self.policy_id,
            "organization_id": self.organization_id,
            "record_id": self.record_id,
            "purpose": self.purpose,
        }.items():
            if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        if not isinstance(self.status, PolicyStatus):
            raise TypeError("status deve ser PolicyStatus.")
        object.__setattr__(
            self,
            "allowed_actions",
            _enum_tuple("allowed_actions", self.allowed_actions, PrivacyAction),
        )
        object.__setattr__(
            self,
            "allowed_legal_bases",
            _enum_tuple(
                "allowed_legal_bases",
                self.allowed_legal_bases,
                DeclaredLegalBasis,
            ),
        )
        object.__setattr__(
            self,
            "allowed_categories",
            _enum_tuple(
                "allowed_categories", self.allowed_categories, DataCategory
            ),
        )
        object.__setattr__(
            self,
            "allowed_roles",
            _safe_tuple("allowed_roles", self.allowed_roles, pattern=_SAFE_ROLE),
        )
        object.__setattr__(
            self,
            "required_scopes",
            _safe_tuple("required_scopes", self.required_scopes),
        )
        object.__setattr__(
            self,
            "allowed_fields",
            _safe_tuple("allowed_fields", self.allowed_fields),
        )
        masked = _safe_tuple(
            "masked_fields", self.masked_fields, required=False
        )
        pseudonymized = _safe_tuple(
            "pseudonymized_fields", self.pseudonymized_fields, required=False
        )
        if not set(masked).issubset(self.allowed_fields):
            raise ValueError("masked_fields deve ser subconjunto de allowed_fields.")
        if not set(pseudonymized).issubset(self.allowed_fields):
            raise ValueError(
                "pseudonymized_fields deve ser subconjunto de allowed_fields."
            )
        if set(masked) & set(pseudonymized):
            raise ValueError("Um campo não pode ter duas proteções incompatíveis.")
        object.__setattr__(self, "masked_fields", masked)
        object.__setattr__(self, "pseudonymized_fields", pseudonymized)
        if self.status is PolicyStatus.ACTIVE:
            if not self.approved_by_hash or not _HEX_DIGEST.fullmatch(
                self.approved_by_hash
            ):
                raise ValueError("Política ativa exige approved_by_hash.")
            if self.approved_at is None or self.approved_at.tzinfo is None:
                raise ValueError("Política ativa exige approved_at com fuso horário.")
        if self.approved_at is not None:
            if self.approved_at.tzinfo is None:
                raise ValueError("approved_at deve possuir fuso horário.")
            object.__setattr__(
                self,
                "approved_at",
                self.approved_at.astimezone(timezone.utc),
            )


class PrivacyPolicyRegistry:
    def __init__(self, policies: Iterable[PrivacyPolicy] = ()) -> None:
        self._policies: dict[tuple[str, str, str], PrivacyPolicy] = {}
        self._lock = RLock()
        for policy in policies:
            self.register(policy)

    def register(self, policy: PrivacyPolicy, *, replace: bool = False) -> None:
        if not isinstance(policy, PrivacyPolicy):
            raise TypeError("policy deve ser PrivacyPolicy.")
        key = (policy.organization_id, policy.record_id, policy.purpose)
        with self._lock:
            if key in self._policies and not replace:
                raise ValueError("Já existe política para este tratamento e finalidade.")
            self._policies[key] = policy

    def find(
        self,
        organization_id: str,
        record_id: str,
        purpose: str,
    ) -> PrivacyPolicy | None:
        with self._lock:
            return self._policies.get((organization_id, record_id, purpose))

    def list_for_organization(self, organization_id: str) -> tuple[PrivacyPolicy, ...]:
        with self._lock:
            policies = tuple(
                policy
                for policy in self._policies.values()
                if policy.organization_id == organization_id
            )
        return tuple(sorted(policies, key=lambda item: item.policy_id))


@dataclass(frozen=True, slots=True)
class PrivacyDecision:
    decision_id: str
    allowed: bool
    reason: PrivacyDecisionReason
    request: DataTreatmentRequest = field(repr=False)
    policy_id: str | None = None


class PrivacyPolicyEngine:
    """Autoriza por política exata e falha fechado em qualquer ambiguidade."""

    def __init__(
        self,
        *,
        inventory: ProcessingInventory,
        policies: PrivacyPolicyRegistry,
        consents: ConsentRegistry,
        minimizer: DataMinimizer,
        audit: InMemoryPrivacyAuditTrail,
        principal_pseudonymizer: Callable[[str, str], str],
    ) -> None:
        self._inventory = inventory
        self._policies = policies
        self._consents = consents
        self._minimizer = minimizer
        self._audit = audit
        self._principal_pseudonymizer = principal_pseudonymizer
        self._allowed_decisions: dict[str, PrivacyDecision] = {}
        self._decision_order: deque[str] = deque()
        self._decision_lock = RLock()

    def authorize(
        self,
        principal: PrivacyPrincipal,
        request: DataTreatmentRequest,
    ) -> PrivacyDecision:
        if principal.organization_id != request.organization_id:
            return self._deny(principal, request, PrivacyDecisionReason.ORGANIZATION_MISMATCH)
        try:
            record = self._inventory.get(request.record_id)
        except KeyError:
            return self._deny(
                principal,
                request,
                PrivacyDecisionReason.TREATMENT_NOT_INVENTORIED,
            )
        policy = self._policies.find(
            request.organization_id,
            request.record_id,
            request.purpose,
        )
        if policy is None:
            return self._deny(principal, request, PrivacyDecisionReason.POLICY_NOT_FOUND)
        if policy.status is not PolicyStatus.ACTIVE:
            return self._deny(
                principal,
                request,
                PrivacyDecisionReason.POLICY_NOT_ACTIVE,
                policy=policy,
            )
        checks = (
            (
                request.action not in policy.allowed_actions,
                PrivacyDecisionReason.ACTION_NOT_ALLOWED,
            ),
            (
                not set(principal.roles) & set(policy.allowed_roles),
                PrivacyDecisionReason.ROLE_NOT_ALLOWED,
            ),
            (
                not set(policy.required_scopes).issubset(principal.scopes),
                PrivacyDecisionReason.SCOPE_MISSING,
            ),
            (
                request.legal_basis not in policy.allowed_legal_bases,
                PrivacyDecisionReason.LEGAL_BASIS_NOT_ALLOWED,
            ),
            (
                not set(request.categories).issubset(record.categories),
                PrivacyDecisionReason.CATEGORY_NOT_INVENTORIED,
            ),
            (
                not set(request.categories).issubset(policy.allowed_categories),
                PrivacyDecisionReason.CATEGORY_NOT_ALLOWED,
            ),
            (
                not set(request.fields).issubset(policy.allowed_fields),
                PrivacyDecisionReason.FIELD_NOT_ALLOWED,
            ),
            (
                record.nature is DataNature.SENSITIVE_PERSONAL
                and not policy.allow_sensitive_processing,
                PrivacyDecisionReason.SENSITIVE_PROCESSING_DENIED,
            ),
            (
                (
                    request.involves_child
                    or DataSubject.CHILD_OR_ADOLESCENT in record.subjects
                )
                and not policy.allow_child_data,
                PrivacyDecisionReason.CHILD_DATA_DENIED,
            ),
            (
                (request.international_transfer or record.international_transfer)
                and not policy.allow_international_transfer,
                PrivacyDecisionReason.INTERNATIONAL_TRANSFER_DENIED,
            ),
        )
        for failed, reason in checks:
            if failed:
                return self._deny(principal, request, reason, policy=policy)

        receipt_id: str | None = None
        if request.legal_basis.requires_consent_receipt:
            if request.subject_id is None:
                return self._deny(
                    principal,
                    request,
                    PrivacyDecisionReason.SUBJECT_REQUIRED,
                    policy=policy,
                )
            receipt = self._consents.find_valid(
                organization_id=request.organization_id,
                subject_id=request.subject_id,
                record_id=request.record_id,
                purpose=request.purpose,
                categories=request.categories,
                receipt_id=request.consent_receipt_id,
            )
            if receipt is None:
                return self._deny(
                    principal,
                    request,
                    PrivacyDecisionReason.CONSENT_MISSING_OR_INVALID,
                    policy=policy,
                )
            receipt_id = receipt.receipt_id

        decision = PrivacyDecision(
            decision_id=new_decision_id(),
            allowed=True,
            reason=PrivacyDecisionReason.ALLOWED,
            request=request,
            policy_id=policy.policy_id,
        )
        self._remember_allowed_decision(decision)
        self._record_audit(principal, decision, receipt_id=receipt_id)
        return decision

    def minimize(
        self,
        decision: PrivacyDecision,
        payload: Mapping[str, Any],
    ) -> DataMinimizationResult:
        if (
            not decision.allowed
            or decision.policy_id is None
            or not self._is_known_allowed_decision(decision)
        ):
            raise PermissionError("Uma decisão permitida é obrigatória.")
        request = decision.request
        policy = self._policies.find(
            request.organization_id,
            request.record_id,
            request.purpose,
        )
        if (
            policy is None
            or policy.status is not PolicyStatus.ACTIVE
            or policy.policy_id != decision.policy_id
        ):
            raise PermissionError("A política da decisão não está mais ativa.")
        return self._minimizer.minimize(
            payload,
            allowed_fields=request.fields,
            masked_fields=set(policy.masked_fields) & set(request.fields),
            pseudonymized_fields=(
                set(policy.pseudonymized_fields) & set(request.fields)
            ),
            namespace=(
                f"privacy:{request.organization_id}:"
                f"{request.record_id}:{request.purpose}"
            ),
        )

    def _remember_allowed_decision(self, decision: PrivacyDecision) -> None:
        with self._decision_lock:
            self._allowed_decisions[decision.decision_id] = decision
            self._decision_order.append(decision.decision_id)
            while len(self._decision_order) > 1000:
                expired_id = self._decision_order.popleft()
                self._allowed_decisions.pop(expired_id, None)

    def _is_known_allowed_decision(self, decision: PrivacyDecision) -> bool:
        with self._decision_lock:
            return self._allowed_decisions.get(decision.decision_id) is decision

    def _deny(
        self,
        principal: PrivacyPrincipal,
        request: DataTreatmentRequest,
        reason: PrivacyDecisionReason,
        *,
        policy: PrivacyPolicy | None = None,
    ) -> PrivacyDecision:
        decision = PrivacyDecision(
            decision_id=new_decision_id(),
            allowed=False,
            reason=reason,
            request=request,
            policy_id=policy.policy_id if policy is not None else None,
        )
        self._record_audit(principal, decision)
        return decision

    def _record_audit(
        self,
        principal: PrivacyPrincipal,
        decision: PrivacyDecision,
        *,
        receipt_id: str | None = None,
    ) -> None:
        request = decision.request
        principal_pseudonym = self._principal_pseudonymizer(
            request.organization_id,
            principal.principal_id,
        )
        principal_hash = hashlib.sha256(principal_pseudonym.encode()).hexdigest()
        receipt_hash = (
            hashlib.sha256(receipt_id.encode()).hexdigest()
            if receipt_id is not None
            else None
        )
        self._audit.append(
            decision_id=decision.decision_id,
            organization_id=request.organization_id,
            principal_hash=principal_hash,
            record_id=request.record_id,
            purpose=request.purpose,
            action=request.action.value,
            outcome=(
                PrivacyAuditOutcome.ALLOWED
                if decision.allowed
                else PrivacyAuditOutcome.DENIED
            ),
            reason=decision.reason.value,
            categories=request.categories,
            requested_field_count=len(request.fields),
            consent_receipt_hash=receipt_hash,
        )
