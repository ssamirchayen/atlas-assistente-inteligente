from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from threading import Thread

import pytest

from atlas.privacy.audit import InMemoryPrivacyAuditTrail
from atlas.privacy.catalog import build_default_privacy_inventory
from atlas.privacy.consent import ConsentRegistry
from atlas.privacy.minimization import DataMinimizer, Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import (
    DeclaredLegalBasis,
    PolicyStatus,
    PrivacyAction,
    PrivacyPolicy,
    PrivacyPolicyEngine,
    PrivacyPolicyRegistry,
    PrivacyPrincipal,
)
from atlas.privacy.rights import (
    InMemoryRightsAuditTrail,
    RightsAuditAction,
    RightsDenialReason,
    RightsExecutionOutcome,
    RightsRequestStatus,
    RightsResponseMode,
    RightsSourceSelection,
    SubjectRight,
    SubjectRightsService,
)
from atlas.privacy.subject_data import InMemorySubjectDataSource


SECRET = b"atlas-test-rights-secret-key-at-least-32-bytes"
NOW = datetime(2026, 2, 3, 10, tzinfo=timezone.utc)
APPROVAL_HASH = hashlib.sha256(b"controller-approved-rights-policy").hexdigest()


class Harness:
    def __init__(
        self,
        *,
        allow_mutations: bool = False,
        retention_reasons: tuple[str, ...] = (),
        with_policy: bool = True,
        max_requests: int = 1000,
        max_audit: int = 1000,
        second_source: bool = False,
    ) -> None:
        self.now = NOW
        self.pseudonymizer = Pseudonymizer(SECRET)
        self.source = self._make_source(
            "session-store",
            retention_reasons=retention_reasons,
        )
        self.sources = [self.source]
        if second_source:
            self.sources.append(self._make_source("session-archive"))
        policies = (self._policy(),) if with_policy else ()
        policy_audit = InMemoryPrivacyAuditTrail(clock=lambda: self.now)
        policy_engine = PrivacyPolicyEngine(
            inventory=build_default_privacy_inventory(),
            policies=PrivacyPolicyRegistry(policies),
            consents=ConsentRegistry(self.pseudonymizer, clock=lambda: self.now),
            minimizer=DataMinimizer(self.pseudonymizer),
            audit=policy_audit,
            principal_pseudonymizer=lambda organization, principal: (
                self.pseudonymizer.pseudonymize(
                    principal,
                    namespace=f"principal:{organization}",
                )
            ),
        )
        self.audit = InMemoryRightsAuditTrail(
            max_events=max_audit,
            clock=lambda: self.now,
        )
        self.service = SubjectRightsService(
            policy_engine=policy_engine,
            pseudonymizer=self.pseudonymizer,
            sources=self.sources,
            audit=self.audit,
            allow_mutations=allow_mutations,
            max_requests=max_requests,
            challenge_ttl=timedelta(minutes=10),
            clock=lambda: self.now,
        )
        self.subject_pseudonym = self.service.subject_pseudonym(
            organization_id="tenant-a",
            subject_id="subject-123",
        )
        for source in self.sources:
            source.put(
                self.subject_pseudonym,
                {
                    "display_name": "Ada Original",
                    "email": "ada@example.test",
                    "preference": "dark",
                },
            )

    @staticmethod
    def _make_source(
        source_id: str,
        *,
        retention_reasons: tuple[str, ...] = (),
    ) -> InMemorySubjectDataSource:
        return InMemorySubjectDataSource(
            source_id=source_id,
            organization_id="tenant-a",
            record_id="session.operational_history",
            categories=(DataCategory.IDENTIFICATION,),
            fields=("display_name", "email", "preference"),
            legal_basis=DeclaredLegalBasis.LEGAL_OBLIGATION,
            retention_reasons=retention_reasons,
        )

    @staticmethod
    def _policy() -> PrivacyPolicy:
        return PrivacyPolicy(
            policy_id="policy.subject.rights",
            organization_id="tenant-a",
            record_id="session.operational_history",
            purpose="fulfill.subject_rights",
            status=PolicyStatus.ACTIVE,
            allowed_actions=(
                PrivacyAction.READ,
                PrivacyAction.UPDATE,
                PrivacyAction.EXPORT,
                PrivacyAction.DELETE,
            ),
            allowed_roles=("privacy-officer",),
            required_scopes=("privacy.rights.execute",),
            allowed_legal_bases=(DeclaredLegalBasis.LEGAL_OBLIGATION,),
            allowed_categories=(DataCategory.IDENTIFICATION,),
            allowed_fields=("display_name", "email", "preference"),
            approved_by_hash=APPROVAL_HASH,
            approved_at=NOW,
        )


def operator(
    principal_id: str = "officer-a",
    *,
    organization_id: str = "tenant-a",
    roles: tuple[str, ...] = ("privacy-officer",),
    scopes: tuple[str, ...] = (
        "privacy.rights.review",
        "privacy.rights.execute",
    ),
) -> PrivacyPrincipal:
    return PrivacyPrincipal(
        principal_id=principal_id,
        organization_id=organization_id,
        roles=roles,
        scopes=scopes,
    )


def selection(
    source_id: str = "session-store",
    fields: tuple[str, ...] = ("display_name", "email"),
) -> RightsSourceSelection:
    return RightsSourceSelection(source_id=source_id, fields=fields)


def submit(
    target: Harness,
    right: SubjectRight = SubjectRight.ACCESS,
    *,
    selections: tuple[RightsSourceSelection, ...] | None = None,
    response_mode: RightsResponseMode = RightsResponseMode.COMPLETE,
):
    return target.service.submit(
        organization_id="tenant-a",
        subject_id="subject-123",
        right=right,
        selections=selections or (selection(),),
        response_mode=response_mode,
    )


def verify(target: Harness, request_id: str):
    challenge = target.service.issue_verification_challenge(
        request_id,
        organization_id="tenant-a",
    )
    return target.service.verify_identity(
        request_id,
        organization_id="tenant-a",
        token=challenge.token,
    )


def approve(target: Harness, request_id: str, *, mutating: bool = False):
    approved = target.service.approve(
        operator("officer-a"),
        request_id,
        confirmation=f"APROVAR {request_id}",
    )
    if mutating:
        approved = target.service.approve(
            operator("officer-b"),
            request_id,
            confirmation=f"APROVAR {request_id}",
        )
    return approved


def ready(
    target: Harness,
    right: SubjectRight = SubjectRight.ACCESS,
    *,
    selections: tuple[RightsSourceSelection, ...] | None = None,
):
    request = submit(target, right, selections=selections)
    verify(target, request.request_id)
    approve(target, request.request_id, mutating=right.mutates_data)
    return target.service.get(request.request_id, organization_id="tenant-a")


def execute(target: Harness, request_id: str, **kwargs: object):
    return target.service.execute(
        operator(),
        request_id,
        confirmation=f"EXECUTAR {request_id}",
        **kwargs,
    )


def test_submit_stores_pseudonym_and_complete_access_deadline() -> None:
    target = Harness()
    request = submit(target)
    assert request.subject_pseudonym.startswith("psn_")
    assert "subject-123" not in repr(request)
    assert request.status is RightsRequestStatus.IDENTITY_PENDING
    assert request.due_at == NOW + timedelta(days=15)
    assert target.audit.list_events()[-1].action is RightsAuditAction.SUBMITTED


def test_simplified_confirmation_is_marked_for_immediate_response() -> None:
    target = Harness()
    request = submit(
        target,
        SubjectRight.CONFIRMATION,
        response_mode=RightsResponseMode.SIMPLIFIED,
    )
    assert request.due_at == NOW


@pytest.mark.parametrize(
    "right",
    [SubjectRight.CORRECTION, SubjectRight.PORTABILITY, SubjectRight.DELETION],
)
def test_non_access_deadline_is_left_for_controller_policy(
    right: SubjectRight,
) -> None:
    assert submit(Harness(), right).due_at is None


def test_submit_rejects_unknown_source_duplicate_and_unknown_field() -> None:
    target = Harness()
    with pytest.raises(KeyError):
        submit(target, selections=(selection("unknown-source"),))
    with pytest.raises(ValueError, match="repetir"):
        submit(target, selections=(selection(), selection()))
    with pytest.raises(ValueError, match="não declarados"):
        submit(target, selections=(selection(fields=("cpf",)),))


def test_get_and_submit_enforce_tenant_isolation() -> None:
    target = Harness()
    request = submit(target)
    with pytest.raises(PermissionError):
        target.service.get(request.request_id, organization_id="tenant-b")
    with pytest.raises(PermissionError):
        target.service.submit(
            organization_id="tenant-b",
            subject_id="subject-123",
            right=SubjectRight.ACCESS,
            selections=(selection(),),
        )


def test_verification_token_is_hidden_and_single_use() -> None:
    target = Harness()
    request = submit(target)
    challenge = target.service.issue_verification_challenge(
        request.request_id,
        organization_id="tenant-a",
    )
    assert challenge.token not in repr(challenge)
    with pytest.raises(PermissionError):
        target.service.verify_identity(
            request.request_id,
            organization_id="tenant-a",
            token="wrong-token",
        )
    verified = target.service.verify_identity(
        request.request_id,
        organization_id="tenant-a",
        token=challenge.token,
    )
    assert verified.status is RightsRequestStatus.VERIFIED
    with pytest.raises(ValueError):
        target.service.verify_identity(
            request.request_id,
            organization_id="tenant-a",
            token=challenge.token,
        )


def test_reissuing_challenge_invalidates_previous_token() -> None:
    target = Harness()
    request = submit(target)
    old = target.service.issue_verification_challenge(
        request.request_id,
        organization_id="tenant-a",
    )
    new = target.service.issue_verification_challenge(
        request.request_id,
        organization_id="tenant-a",
    )
    with pytest.raises(PermissionError):
        target.service.verify_identity(
            request.request_id,
            organization_id="tenant-a",
            token=old.token,
        )
    verified = target.service.verify_identity(
        request.request_id,
        organization_id="tenant-a",
        token=new.token,
    )
    assert verified.status is RightsRequestStatus.VERIFIED


def test_expired_challenge_blocks_request() -> None:
    target = Harness()
    request = submit(target)
    challenge = target.service.issue_verification_challenge(
        request.request_id,
        organization_id="tenant-a",
    )
    target.now += timedelta(minutes=10)
    with pytest.raises(PermissionError, match="expirou"):
        target.service.verify_identity(
            request.request_id,
            organization_id="tenant-a",
            token=challenge.token,
        )
    blocked = target.service.get(request.request_id, organization_id="tenant-a")
    assert blocked.status is RightsRequestStatus.BLOCKED
    assert blocked.denial_reason is RightsDenialReason.IDENTITY_FAILED


def test_five_invalid_tokens_block_request() -> None:
    target = Harness()
    request = submit(target)
    target.service.issue_verification_challenge(
        request.request_id,
        organization_id="tenant-a",
    )
    for _ in range(5):
        with pytest.raises(PermissionError):
            target.service.verify_identity(
                request.request_id,
                organization_id="tenant-a",
                token="wrong-token",
            )
    assert target.service.get(
        request.request_id,
        organization_id="tenant-a",
    ).status is RightsRequestStatus.BLOCKED


def test_approval_requires_verified_identity_and_exact_confirmation() -> None:
    target = Harness()
    request = submit(target)
    with pytest.raises(ValueError):
        approve(target, request.request_id)
    verify(target, request.request_id)
    with pytest.raises(PermissionError, match="confirmação"):
        target.service.approve(
            operator(),
            request.request_id,
            confirmation="APROVAR OUTRO",
        )


@pytest.mark.parametrize(
    "principal",
    [
        operator(roles=("viewer",)),
        operator(scopes=("privacy.rights.execute",)),
        operator(organization_id="tenant-b"),
    ],
)
def test_approval_enforces_role_scope_and_tenant(
    principal: PrivacyPrincipal,
) -> None:
    target = Harness()
    request = submit(target)
    verify(target, request.request_id)
    with pytest.raises(PermissionError):
        target.service.approve(
            principal,
            request.request_id,
            confirmation=f"APROVAR {request.request_id}",
        )


def test_read_only_request_needs_one_approval() -> None:
    target = Harness()
    request = submit(target)
    verify(target, request.request_id)
    approved = approve(target, request.request_id)
    assert approved.status is RightsRequestStatus.APPROVED
    assert len(approved.approval_hashes) == 1


def test_mutating_request_needs_two_distinct_approvals() -> None:
    target = Harness()
    request = submit(target, SubjectRight.CORRECTION)
    verify(target, request.request_id)
    first = target.service.approve(
        operator("officer-a"),
        request.request_id,
        confirmation=f"APROVAR {request.request_id}",
    )
    repeated = target.service.approve(
        operator("officer-a"),
        request.request_id,
        confirmation=f"APROVAR {request.request_id}",
    )
    second = target.service.approve(
        operator("officer-b"),
        request.request_id,
        confirmation=f"APROVAR {request.request_id}",
    )
    assert first.status is RightsRequestStatus.VERIFIED
    assert repeated == first
    assert second.status is RightsRequestStatus.APPROVED
    assert len(second.approval_hashes) == 2


def test_verified_request_can_be_denied_with_structured_reason() -> None:
    target = Harness()
    request = submit(target)
    verify(target, request.request_id)
    denied = target.service.deny(
        operator(),
        request.request_id,
        reason=RightsDenialReason.NOT_CONTROLLER,
    )
    assert denied.status is RightsRequestStatus.DENIED
    assert denied.denial_reason is RightsDenialReason.NOT_CONTROLLER


def test_execution_requires_approval_and_exact_confirmation() -> None:
    target = Harness()
    request = submit(target)
    verify(target, request.request_id)
    with pytest.raises(PermissionError, match="aprovada"):
        execute(target, request.request_id)
    approve(target, request.request_id)
    with pytest.raises(PermissionError, match="confirmação"):
        target.service.execute(
            operator(),
            request.request_id,
            confirmation="EXECUTAR OUTRO",
        )


def test_missing_privacy_policy_blocks_execution() -> None:
    target = Harness(with_policy=False)
    request = ready(target)
    result = execute(target, request.request_id)
    assert result.outcome is RightsExecutionOutcome.BLOCKED
    assert result.reason == "policy_policy_not_found"
    assert target.service.get(
        request.request_id,
        organization_id="tenant-a",
    ).denial_reason is RightsDenialReason.POLICY_DENIED


def test_confirmation_returns_only_existence_metadata() -> None:
    target = Harness()
    request = ready(target, SubjectRight.CONFIRMATION)
    result = execute(target, request.request_id)
    assert result.outcome is RightsExecutionOutcome.COMPLETED
    assert dict(result.payload) == {"session-store": True}
    assert "Ada Original" not in repr(result)


def test_access_returns_only_authorized_fields_without_persisting_payload() -> None:
    target = Harness()
    request = ready(
        target,
        SubjectRight.ACCESS,
        selections=(selection(fields=("display_name",)),),
    )
    result = execute(target, request.request_id)
    assert dict(result.payload["session-store"]) == {
        "display_name": "Ada Original"
    }
    assert "ada@example.test" not in repr(result)
    assert "Ada Original" not in repr(target.audit.list_events())


def test_portability_uses_export_policy_action() -> None:
    target = Harness()
    request = ready(target, SubjectRight.PORTABILITY)
    result = execute(target, request.request_id)
    assert result.outcome is RightsExecutionOutcome.COMPLETED
    assert set(result.payload["session-store"]) == {"display_name", "email"}


def test_correction_is_dry_run_by_default_and_does_not_store_values() -> None:
    target = Harness()
    request = ready(target, SubjectRight.CORRECTION)
    result = execute(
        target,
        request.request_id,
        corrections={
            "session-store": {
                "display_name": "Ada Corrected",
                "email": "new@example.test",
            }
        },
    )
    assert result.outcome is RightsExecutionOutcome.PLANNED
    assert target.source.read(
        target.subject_pseudonym,
        ("display_name",),
    )["display_name"] == "Ada Original"
    assert "Ada Corrected" not in repr(result)
    assert target.service.get(
        request.request_id,
        organization_id="tenant-a",
    ).status is RightsRequestStatus.APPROVED


def test_live_correction_requires_two_approvals_and_updates_one_source() -> None:
    target = Harness(allow_mutations=True)
    request = ready(
        target,
        SubjectRight.CORRECTION,
        selections=(selection(fields=("email",)),),
    )
    result = execute(
        target,
        request.request_id,
        corrections={"session-store": {"email": "new@example.test"}},
    )
    assert result.outcome is RightsExecutionOutcome.COMPLETED
    assert target.source.read(target.subject_pseudonym, ("email",))["email"] == (
        "new@example.test"
    )


def test_correction_fields_must_match_selection() -> None:
    target = Harness(allow_mutations=True)
    request = ready(
        target,
        SubjectRight.CORRECTION,
        selections=(selection(fields=("email",)),),
    )
    with pytest.raises(ValueError, match="coincidir"):
        execute(
            target,
            request.request_id,
            corrections={"session-store": {"display_name": "Ada"}},
        )
    assert target.source.read(target.subject_pseudonym, ("email",))["email"] == (
        "ada@example.test"
    )


def test_deletion_is_dry_run_by_default() -> None:
    target = Harness()
    request = ready(target, SubjectRight.DELETION)
    result = execute(target, request.request_id)
    assert result.outcome is RightsExecutionOutcome.PLANNED
    assert result.mutation_plans[0].record_count == 1
    assert target.source.has_subject(target.subject_pseudonym) is True


def test_retention_restriction_blocks_deletion() -> None:
    target = Harness(
        allow_mutations=True,
        retention_reasons=("legal_obligation",),
    )
    request = ready(target, SubjectRight.DELETION)
    result = execute(target, request.request_id)
    assert result.outcome is RightsExecutionOutcome.BLOCKED
    assert result.reason == RightsDenialReason.RETENTION_REQUIRED.value
    assert result.mutation_plans[0].retention_reasons == ("legal_obligation",)
    assert target.source.has_subject(target.subject_pseudonym) is True


def test_live_deletion_removes_subject_after_two_approvals() -> None:
    target = Harness(allow_mutations=True)
    request = ready(target, SubjectRight.DELETION)
    result = execute(target, request.request_id)
    assert result.outcome is RightsExecutionOutcome.COMPLETED
    assert target.source.has_subject(target.subject_pseudonym) is False


def test_multi_source_live_mutation_is_blocked_before_changes() -> None:
    target = Harness(allow_mutations=True, second_source=True)
    selections = (
        selection("session-store", ("email",)),
        selection("session-archive", ("email",)),
    )
    request = ready(target, SubjectRight.DELETION, selections=selections)
    result = execute(target, request.request_id)
    assert result.outcome is RightsExecutionOutcome.BLOCKED
    assert result.reason == RightsDenialReason.UNSUPPORTED_ATOMIC_MUTATION.value
    assert all(
        source.has_subject(target.subject_pseudonym) for source in target.sources
    )


def test_completed_request_is_idempotent_and_does_not_redeliver_payload() -> None:
    target = Harness()
    request = ready(target)
    first = execute(target, request.request_id)
    replay = execute(target, request.request_id)
    assert first.payload
    assert replay.outcome is RightsExecutionOutcome.ALREADY_COMPLETED
    assert replay.replayed is True
    assert not replay.payload


def test_audit_is_bounded_filtered_and_contains_no_raw_identifiers() -> None:
    target = Harness(max_audit=3)
    request = ready(target)
    execute(target, request.request_id)
    events = target.audit.list_events()
    assert len(events) == 3
    assert len(target.audit.list_events(organization_id="tenant-a")) == 3
    assert target.audit.list_events(organization_id="tenant-b") == ()
    event_text = repr(events)
    assert "subject-123" not in event_text
    assert "officer-a" not in event_text
    assert "Ada Original" not in event_text


def test_request_capacity_never_evicts_active_request() -> None:
    target = Harness(max_requests=1)
    first = submit(target)
    with pytest.raises(OverflowError, match="limite"):
        submit(target)
    verify(target, first.request_id)
    approve(target, first.request_id)
    execute(target, first.request_id)
    second = submit(target)
    with pytest.raises(KeyError):
        target.service.get(first.request_id, organization_id="tenant-a")
    assert second.status is RightsRequestStatus.IDENTITY_PENDING


def test_concurrent_distinct_approvals_remain_consistent() -> None:
    target = Harness()
    request = submit(target, SubjectRight.DELETION)
    verify(target, request.request_id)
    errors: list[Exception] = []

    def worker(name: str) -> None:
        try:
            target.service.approve(
                operator(name),
                request.request_id,
                confirmation=f"APROVAR {request.request_id}",
            )
        except Exception as error:  # pragma: no cover - diagnostic collection
            errors.append(error)

    threads = [Thread(target=worker, args=(f"officer-{index}",)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    approved = target.service.get(request.request_id, organization_id="tenant-a")
    assert errors == []
    assert approved.status is RightsRequestStatus.APPROVED
    assert len(approved.approval_hashes) == 2


def test_sprint24_stage3_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "privacy_rights_pilot.py").is_file()
    assert (
        root / "docs" / "SPRINT24_ETAPA3_DIREITOS_TITULARES.md"
    ).is_file()
    assert (root / "docs" / "SPRINT24_ETAPA3_VALIDACAO.md").is_file()
