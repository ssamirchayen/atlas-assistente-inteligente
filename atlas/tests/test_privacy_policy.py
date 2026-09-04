from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path

import pytest

from atlas.privacy.audit import InMemoryPrivacyAuditTrail, PrivacyAuditOutcome
from atlas.privacy.catalog import build_default_privacy_inventory
from atlas.privacy.consent import ConsentRegistry
from atlas.privacy.minimization import DataMinimizer, Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import (
    DataTreatmentRequest,
    DeclaredLegalBasis,
    PolicyStatus,
    PrivacyAction,
    PrivacyDecisionReason,
    PrivacyPolicy,
    PrivacyPolicyEngine,
    PrivacyPolicyRegistry,
    PrivacyPrincipal,
)


SECRET = b"atlas-test-privacy-secret-key-32-bytes-minimum"
NOW = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
APPROVER_HASH = hashlib.sha256(b"controller-approval").hexdigest()


class Harness:
    def __init__(self, policy: PrivacyPolicy | None = None) -> None:
        self.now = NOW
        self.pseudonymizer = Pseudonymizer(SECRET)
        self.consents = ConsentRegistry(
            self.pseudonymizer,
            clock=lambda: self.now,
        )
        self.audit = InMemoryPrivacyAuditTrail(
            max_events=100,
            clock=lambda: self.now,
        )
        self.registry = PrivacyPolicyRegistry((policy,) if policy else ())
        self.engine = PrivacyPolicyEngine(
            inventory=build_default_privacy_inventory(),
            policies=self.registry,
            consents=self.consents,
            minimizer=DataMinimizer(self.pseudonymizer),
            audit=self.audit,
            principal_pseudonymizer=lambda organization, principal: (
                self.pseudonymizer.pseudonymize(
                    principal,
                    namespace=f"principal:{organization}",
                )
            ),
        )


def policy(**overrides: object) -> PrivacyPolicy:
    values: dict[str, object] = {
        "policy_id": "policy.memory.preference",
        "organization_id": "tenant-a",
        "record_id": "memory.long_term_and_embeddings",
        "purpose": "remember.preference",
        "status": PolicyStatus.ACTIVE,
        "allowed_actions": (PrivacyAction.READ,),
        "allowed_roles": ("privacy-operator",),
        "required_scopes": ("memory.read",),
        "allowed_legal_bases": (DeclaredLegalBasis.SENSITIVE_SPECIFIC_CONSENT,),
        "allowed_categories": (
            DataCategory.CONVERSATION,
            DataCategory.PREFERENCES,
        ),
        "allowed_fields": ("content", "category", "source"),
        "masked_fields": ("content",),
        "pseudonymized_fields": ("source",),
        "approved_by_hash": APPROVER_HASH,
        "approved_at": NOW,
        "allow_sensitive_processing": True,
    }
    values.update(overrides)
    return PrivacyPolicy(**values)


def principal(**overrides: object) -> PrivacyPrincipal:
    values: dict[str, object] = {
        "principal_id": "operator-123",
        "organization_id": "tenant-a",
        "roles": ("privacy-operator",),
        "scopes": ("memory.read",),
    }
    values.update(overrides)
    return PrivacyPrincipal(**values)


def request(**overrides: object) -> DataTreatmentRequest:
    values: dict[str, object] = {
        "organization_id": "tenant-a",
        "record_id": "memory.long_term_and_embeddings",
        "purpose": "remember.preference",
        "action": PrivacyAction.READ,
        "legal_basis": DeclaredLegalBasis.SENSITIVE_SPECIFIC_CONSENT,
        "categories": (DataCategory.CONVERSATION,),
        "fields": ("content", "source"),
        "subject_id": "subject-123",
    }
    values.update(overrides)
    return DataTreatmentRequest(**values)


def authorize_with_valid_consent(target: Harness):
    receipt = target.consents.grant(
        organization_id="tenant-a",
        subject_id="subject-123",
        record_id="memory.long_term_and_embeddings",
        purpose="remember.preference",
        categories=(DataCategory.CONVERSATION,),
        evidence="Consent screen version 3 accepted",
        granted_by="privacy-admin",
        expires_at=target.now + timedelta(days=30),
    )
    return target.engine.authorize(
        principal(),
        request(consent_receipt_id=receipt.receipt_id),
    ), receipt


def assert_denied(
    target: Harness,
    reason: PrivacyDecisionReason,
    *,
    principal_value: PrivacyPrincipal | None = None,
    request_value: DataTreatmentRequest | None = None,
) -> None:
    decision = target.engine.authorize(
        principal_value or principal(),
        request_value or request(),
    )
    assert decision.allowed is False
    assert decision.reason is reason
    assert target.audit.list_events()[-1].outcome is PrivacyAuditOutcome.DENIED


def test_engine_fails_closed_without_exact_policy() -> None:
    assert_denied(Harness(), PrivacyDecisionReason.POLICY_NOT_FOUND)


@pytest.mark.parametrize("status", [PolicyStatus.DRAFT, PolicyStatus.SUSPENDED])
def test_engine_denies_non_active_policy(status: PolicyStatus) -> None:
    assert_denied(
        Harness(
            policy(
                status=status,
                approved_by_hash=None,
                approved_at=None,
            )
        ),
        PrivacyDecisionReason.POLICY_NOT_ACTIVE,
    )


def test_engine_enforces_tenant_isolation() -> None:
    assert_denied(
        Harness(policy()),
        PrivacyDecisionReason.ORGANIZATION_MISMATCH,
        principal_value=principal(organization_id="tenant-b"),
    )


def test_engine_denies_treatment_missing_from_inventory() -> None:
    assert_denied(
        Harness(),
        PrivacyDecisionReason.TREATMENT_NOT_INVENTORIED,
        request_value=request(record_id="unknown.data_flow"),
    )


@pytest.mark.parametrize(
    ("policy_overrides", "principal_overrides", "request_overrides", "reason"),
    [
        ({}, {}, {"action": PrivacyAction.EXPORT}, PrivacyDecisionReason.ACTION_NOT_ALLOWED),
        ({}, {"roles": ("viewer",)}, {}, PrivacyDecisionReason.ROLE_NOT_ALLOWED),
        ({}, {"scopes": ("memory.list",)}, {}, PrivacyDecisionReason.SCOPE_MISSING),
        (
            {},
            {},
            {"legal_basis": DeclaredLegalBasis.SENSITIVE_LEGAL_OBLIGATION},
            PrivacyDecisionReason.LEGAL_BASIS_NOT_ALLOWED,
        ),
        (
            {},
            {},
            {"categories": (DataCategory.FINANCIAL,)},
            PrivacyDecisionReason.CATEGORY_NOT_INVENTORIED,
        ),
        (
            {"allowed_categories": (DataCategory.PREFERENCES,)},
            {},
            {},
            PrivacyDecisionReason.CATEGORY_NOT_ALLOWED,
        ),
        ({}, {}, {"fields": ("raw_secret",)}, PrivacyDecisionReason.FIELD_NOT_ALLOWED),
    ],
)
def test_engine_enforces_declared_policy_boundaries(
    policy_overrides: dict[str, object],
    principal_overrides: dict[str, object],
    request_overrides: dict[str, object],
    reason: PrivacyDecisionReason,
) -> None:
    assert_denied(
        Harness(policy(**policy_overrides)),
        reason,
        principal_value=principal(**principal_overrides),
        request_value=request(**request_overrides),
    )


def test_sensitive_data_is_denied_by_default() -> None:
    assert_denied(
        Harness(policy(allow_sensitive_processing=False)),
        PrivacyDecisionReason.SENSITIVE_PROCESSING_DENIED,
    )


def test_child_data_requires_explicit_policy_permission() -> None:
    assert_denied(
        Harness(policy()),
        PrivacyDecisionReason.CHILD_DATA_DENIED,
        request_value=request(involves_child=True),
    )


def test_international_transfer_requires_explicit_policy_permission() -> None:
    assert_denied(
        Harness(policy()),
        PrivacyDecisionReason.INTERNATIONAL_TRANSFER_DENIED,
        request_value=request(international_transfer=True),
    )


def test_consent_basis_requires_identified_subject() -> None:
    assert_denied(
        Harness(policy()),
        PrivacyDecisionReason.SUBJECT_REQUIRED,
        request_value=request(subject_id=None),
    )


def test_consent_basis_requires_valid_scoped_receipt() -> None:
    assert_denied(
        Harness(policy()),
        PrivacyDecisionReason.CONSENT_MISSING_OR_INVALID,
    )


def test_revoked_consent_is_denied() -> None:
    target = Harness(policy())
    decision, receipt = authorize_with_valid_consent(target)
    assert decision.allowed is True
    target.consents.revoke(
        receipt.receipt_id,
        organization_id="tenant-a",
        revoked_by="privacy-admin",
    )
    assert_denied(
        target,
        PrivacyDecisionReason.CONSENT_MISSING_OR_INVALID,
        request_value=request(consent_receipt_id=receipt.receipt_id),
    )


def test_valid_consent_allows_and_is_audited_without_raw_receipt() -> None:
    target = Harness(policy())
    decision, receipt = authorize_with_valid_consent(target)
    event = target.audit.list_events()[-1]
    assert decision.allowed is True
    assert decision.reason is PrivacyDecisionReason.ALLOWED
    assert event.outcome is PrivacyAuditOutcome.ALLOWED
    assert event.consent_receipt_hash == hashlib.sha256(
        receipt.receipt_id.encode()
    ).hexdigest()
    assert receipt.receipt_id not in repr(event)


def test_non_consent_legal_basis_does_not_require_receipt() -> None:
    target = Harness(
        policy(
            allowed_legal_bases=(DeclaredLegalBasis.SENSITIVE_LEGAL_OBLIGATION,),
        )
    )
    decision = target.engine.authorize(
        principal(),
        request(
            legal_basis=DeclaredLegalBasis.SENSITIVE_LEGAL_OBLIGATION,
            subject_id=None,
        ),
    )
    assert decision.allowed is True


def test_allowed_decision_minimizes_masks_and_pseudonymizes_payload() -> None:
    target = Harness(policy())
    decision, _ = authorize_with_valid_consent(target)
    result = target.engine.minimize(
        decision,
        {
            "content": "private message 1234",
            "source": "device-007",
            "internal_debug": "must disappear",
        },
    )
    assert result.data["content"] == "***1234"
    assert str(result.data["source"]).startswith("psn_")
    assert "internal_debug" not in result.data
    assert result.dropped_fields == ("internal_debug",)


def test_denied_decision_cannot_minimize_payload() -> None:
    target = Harness()
    denied = target.engine.authorize(principal(), request())
    with pytest.raises(PermissionError):
        target.engine.minimize(denied, {"content": "private"})


def test_fabricated_copy_of_decision_cannot_minimize_payload() -> None:
    target = Harness(policy())
    decision, _ = authorize_with_valid_consent(target)
    fabricated = replace(decision)
    with pytest.raises(PermissionError):
        target.engine.minimize(fabricated, {"content": "private"})


def test_policy_change_invalidates_previous_decision() -> None:
    target = Harness(policy())
    decision, _ = authorize_with_valid_consent(target)
    target.registry.register(
        policy(
            policy_id="policy.memory.suspended",
            status=PolicyStatus.SUSPENDED,
            approved_by_hash=None,
            approved_at=None,
        ),
        replace=True,
    )
    with pytest.raises(PermissionError, match="não está mais ativa"):
        target.engine.minimize(decision, {"content": "private"})


def test_audit_contains_only_metadata_and_hashed_principal() -> None:
    target = Harness(policy())
    decision, _ = authorize_with_valid_consent(target)
    target.engine.minimize(decision, {"content": "raw-private-value"})
    event_text = repr(target.audit.list_events()[-1])
    assert "operator-123" not in event_text
    assert "subject-123" not in event_text
    assert "raw-private-value" not in event_text
    assert target.audit.list_events()[-1].requested_field_count == 2


def test_audit_is_bounded_and_tenant_filtered() -> None:
    audit = InMemoryPrivacyAuditTrail(max_events=2, clock=lambda: NOW)
    common = {
        "principal_hash": "a" * 64,
        "record_id": "memory.long_term_and_embeddings",
        "purpose": "remember.preference",
        "action": "read",
        "outcome": PrivacyAuditOutcome.DENIED,
        "reason": "policy_not_found",
        "categories": (DataCategory.CONVERSATION,),
        "requested_field_count": 1,
    }
    audit.append(decision_id="1" * 32, organization_id="tenant-a", **common)
    audit.append(decision_id="2" * 32, organization_id="tenant-b", **common)
    audit.append(decision_id="3" * 32, organization_id="tenant-a", **common)
    assert [event.decision_id for event in audit.list_events()] == [
        "2" * 32,
        "3" * 32,
    ]
    assert len(audit.list_events(organization_id="tenant-a")) == 1


def test_policy_registry_rejects_duplicate_and_allows_explicit_replace() -> None:
    registry = PrivacyPolicyRegistry((policy(),))
    with pytest.raises(ValueError, match="Já existe"):
        registry.register(policy(policy_id="policy.memory.other"))
    replacement = policy(policy_id="policy.memory.replacement")
    registry.register(replacement, replace=True)
    assert registry.list_for_organization("tenant-a") == (replacement,)
    assert registry.list_for_organization("tenant-b") == ()


def test_active_policy_requires_controller_approval_evidence() -> None:
    with pytest.raises(ValueError, match="approved_by_hash"):
        policy(approved_by_hash=None)
    with pytest.raises(ValueError, match="approved_at"):
        policy(approved_at=None)


def test_policy_rejects_ambiguous_field_protection() -> None:
    with pytest.raises(ValueError, match="duas proteções"):
        policy(
            masked_fields=("content",),
            pseudonymized_fields=("content",),
        )


def test_sprint24_stage2_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "privacy_policy_pilot.py").is_file()
    assert (
        root / "docs" / "SPRINT24_ETAPA2_PRIVACY_POLICY_ENGINE.md"
    ).is_file()
    assert (root / "docs" / "SPRINT24_ETAPA2_VALIDACAO.md").is_file()
