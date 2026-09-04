from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from threading import Thread

import pytest

from atlas.privacy.disposal import (
    DisposalAuditAction,
    DisposalCoordinator,
    DisposalOutcome,
    DisposalPlanStatus,
    InMemoryDisposalAuditTrail,
    NotificationStatus,
)
from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import DeclaredLegalBasis, PrivacyPrincipal
from atlas.privacy.retention import (
    InMemoryRetentionAuditTrail,
    LegalHold,
    LegalHoldRegistry,
    LifecycleAction,
    RetentionCandidate,
    RetentionEngine,
    RetentionPolicyRegistry,
    RetentionRule,
    RetentionRuleStatus,
    RetentionTrigger,
)
from atlas.privacy.subject_data import InMemorySubjectDataSource


NOW = datetime(2026, 2, 3, 10, tzinfo=timezone.utc)
SECRET = b"atlas-disposal-test-secret-at-least-32-bytes"
APPROVAL_HASH = hashlib.sha256(b"retention-approval").hexdigest()


class CountingSource(InMemorySubjectDataSource):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.delete_calls = 0

    def delete(self, subject_pseudonym: str) -> int:
        self.delete_calls += 1
        return super().delete(subject_pseudonym)


def retention_rule(**changes: object) -> RetentionRule:
    values: dict[str, object] = {
        "rule_id": "rule.session.retention",
        "organization_id": "tenant-a",
        "record_id": "session.operational_history",
        "status": RetentionRuleStatus.ACTIVE,
        "trigger": RetentionTrigger.CREATED_AT,
        "retention_period": timedelta(days=30),
        "grace_period": timedelta(0),
        "action": LifecycleAction.DELETE,
        "version": 1,
        "processor_ids": ("processor.crm", "processor.archive"),
        "approved_by_hash": APPROVAL_HASH,
        "approved_at": NOW,
    }
    values.update(changes)
    return RetentionRule(**values)


def officer(
    principal_id: str = "officer-a",
    *,
    organization_id: str = "tenant-a",
    roles: tuple[str, ...] = ("privacy-officer",),
    scopes: tuple[str, ...] = (
        "privacy.retention.approve",
        "privacy.retention.execute",
    ),
) -> PrivacyPrincipal:
    return PrivacyPrincipal(
        principal_id=principal_id,
        organization_id=organization_id,
        roles=roles,
        scopes=scopes,
    )


class Harness:
    def __init__(
        self,
        *,
        allow_mutations: bool = False,
        action: LifecycleAction = LifecycleAction.DELETE,
        retention_reasons: tuple[str, ...] = (),
        with_rule: bool = True,
        max_audit: int = 1000,
    ) -> None:
        self.now = NOW
        self.pseudonymizer = Pseudonymizer(SECRET)
        self.subject = self.pseudonymizer.pseudonymize(
            "subject-123",
            namespace="rights:tenant-a:subject",
        )
        self.source = CountingSource(
            source_id="session-store",
            organization_id="tenant-a",
            record_id="session.operational_history",
            categories=(DataCategory.IDENTIFICATION,),
            fields=("display_name", "email"),
            legal_basis=DeclaredLegalBasis.LEGAL_OBLIGATION,
            retention_reasons=retention_reasons,
        )
        self.source.put(
            self.subject,
            {"display_name": "Ada", "email": "ada@example.test"},
        )
        rules = (retention_rule(action=action),) if with_rule else ()
        self.policies = RetentionPolicyRegistry(rules)
        self.holds = LegalHoldRegistry()
        self.retention_audit = InMemoryRetentionAuditTrail(
            clock=lambda: self.now
        )
        self.engine = RetentionEngine(
            policies=self.policies,
            legal_holds=self.holds,
            audit=self.retention_audit,
            clock=lambda: self.now,
        )
        self.audit = InMemoryDisposalAuditTrail(
            max_events=max_audit,
            clock=lambda: self.now,
        )
        self.coordinator = DisposalCoordinator(
            retention_engine=self.engine,
            pseudonymizer=self.pseudonymizer,
            sources=(self.source,),
            audit=self.audit,
            allow_mutations=allow_mutations,
            plan_ttl=timedelta(minutes=15),
            clock=lambda: self.now,
        )

    def candidate(self, **changes: object) -> RetentionCandidate:
        values: dict[str, object] = {
            "candidate_id": "candidate-session-001",
            "organization_id": "tenant-a",
            "source_id": "session-store",
            "record_id": "session.operational_history",
            "subject_pseudonym": self.subject,
            "created_at": NOW - timedelta(days=40),
        }
        values.update(changes)
        return RetentionCandidate(**values)

    def approved_plan(self):
        plan = self.coordinator.create_plan(self.candidate())
        self.coordinator.approve(
            officer("officer-a"),
            plan.plan_id,
            confirmation=f"APROVAR {plan.plan_id}",
        )
        return self.coordinator.approve(
            officer("officer-b"),
            plan.plan_id,
            confirmation=f"APROVAR {plan.plan_id}",
        )


def execute(target: Harness, plan_id: str):
    return target.coordinator.execute(
        officer(),
        plan_id,
        confirmation=f"EXECUTAR {plan_id}",
    )


def test_create_plan_contains_only_metadata_and_hides_subject() -> None:
    target = Harness()
    plan = target.coordinator.create_plan(target.candidate())
    assert plan.status is DisposalPlanStatus.PENDING_APPROVAL
    assert plan.record_count == 1
    assert plan.subject_hash == target.candidate().subject_hash
    assert target.subject not in repr(plan)
    assert "ada@example.test" not in repr(plan)


def test_create_plan_fails_closed_without_retention_rule() -> None:
    target = Harness(with_rule=False)
    with pytest.raises(PermissionError, match="no_policy"):
        target.coordinator.create_plan(target.candidate())


def test_create_plan_rejects_record_not_yet_due() -> None:
    target = Harness()
    with pytest.raises(PermissionError, match="not_due"):
        target.coordinator.create_plan(
            target.candidate(created_at=NOW - timedelta(days=5))
        )


def test_create_plan_rejects_source_retention_impediment() -> None:
    target = Harness(retention_reasons=("legal.obligation",))
    with pytest.raises(PermissionError, match="impedimento"):
        target.coordinator.create_plan(target.candidate())


def test_create_plan_rejects_tenant_mismatch() -> None:
    target = Harness()
    with pytest.raises(PermissionError, match="não corresponde"):
        target.coordinator.create_plan(
            target.candidate(organization_id="tenant-b")
        )


def test_approval_requires_exact_confirmation() -> None:
    target = Harness()
    plan = target.coordinator.create_plan(target.candidate())
    with pytest.raises(PermissionError, match="confirmação"):
        target.coordinator.approve(
            officer(),
            plan.plan_id,
            confirmation="SIM",
        )


@pytest.mark.parametrize(
    "principal",
    (
        officer(roles=("admin",)),
        officer(scopes=("privacy.retention.execute",)),
        officer(organization_id="tenant-b"),
    ),
)
def test_approval_requires_tenant_role_and_scope(
    principal: PrivacyPrincipal,
) -> None:
    target = Harness()
    plan = target.coordinator.create_plan(target.candidate())
    with pytest.raises(PermissionError):
        target.coordinator.approve(
            principal,
            plan.plan_id,
            confirmation=f"APROVAR {plan.plan_id}",
        )


def test_delete_requires_two_distinct_approvals() -> None:
    target = Harness()
    plan = target.coordinator.create_plan(target.candidate())
    first = target.coordinator.approve(
        officer("officer-a"),
        plan.plan_id,
        confirmation=f"APROVAR {plan.plan_id}",
    )
    duplicate = target.coordinator.approve(
        officer("officer-a"),
        plan.plan_id,
        confirmation=f"APROVAR {plan.plan_id}",
    )
    assert first.status is DisposalPlanStatus.PENDING_APPROVAL
    assert duplicate.approval_hashes == first.approval_hashes
    with pytest.raises(PermissionError, match="aprovações"):
        execute(target, plan.plan_id)


def test_second_distinct_approval_releases_plan() -> None:
    target = Harness()
    plan = target.approved_plan()
    assert plan.status is DisposalPlanStatus.APPROVED
    assert len(plan.approval_hashes) == 2


def test_execute_requires_exact_confirmation() -> None:
    target = Harness()
    plan = target.approved_plan()
    with pytest.raises(PermissionError, match="confirmação"):
        target.coordinator.execute(
            officer(),
            plan.plan_id,
            confirmation="EXECUTAR outro-plano",
        )


def test_dry_run_is_default_and_does_not_delete() -> None:
    target = Harness()
    plan = target.approved_plan()
    result = execute(target, plan.plan_id)
    assert result.outcome is DisposalOutcome.PLANNED
    assert result.reason == "dry_run"
    assert target.source.has_subject(target.subject) is True
    assert target.source.delete_calls == 0


def test_live_execution_deletes_once_and_builds_receipt() -> None:
    target = Harness(allow_mutations=True)
    plan = target.approved_plan()
    result = execute(target, plan.plan_id)
    assert result.outcome is DisposalOutcome.EXECUTED
    assert result.affected_count == 1
    assert result.receipt is not None
    assert result.receipt.plan_id == plan.plan_id
    assert result.receipt.affected_count == 1
    assert target.source.has_subject(target.subject) is False
    assert target.source.delete_calls == 1
    assert target.coordinator.get(
        plan.plan_id,
        organization_id="tenant-a",
    ).status is DisposalPlanStatus.EXECUTED


def test_receipt_never_contains_payload_or_raw_subject() -> None:
    target = Harness(allow_mutations=True)
    result = execute(target, target.approved_plan().plan_id)
    text = repr(result.receipt)
    assert "ada@example.test" not in text
    assert target.subject not in text
    assert result.receipt.subject_hash == target.candidate().subject_hash


def test_execution_creates_notification_tasks_without_sending() -> None:
    target = Harness(allow_mutations=True)
    result = execute(target, target.approved_plan().plan_id)
    assert {task.processor_id for task in result.notification_tasks} == {
        "processor.crm",
        "processor.archive",
    }
    assert all(
        task.status is NotificationStatus.PENDING
        for task in result.notification_tasks
    )


def test_execution_is_idempotent_and_does_not_repeat_delete() -> None:
    target = Harness(allow_mutations=True)
    plan = target.approved_plan()
    first = execute(target, plan.plan_id)
    second = execute(target, plan.plan_id)
    assert first.outcome is DisposalOutcome.EXECUTED
    assert second.outcome is DisposalOutcome.ALREADY_EXECUTED
    assert second.replayed is True
    assert second.receipt == first.receipt
    assert target.source.delete_calls == 1


def test_concurrent_execution_deletes_only_once() -> None:
    target = Harness(allow_mutations=True)
    plan = target.approved_plan()
    results = []

    def run() -> None:
        results.append(execute(target, plan.plan_id))

    threads = [Thread(target=run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert target.source.delete_calls == 1
    assert sum(result.outcome is DisposalOutcome.EXECUTED for result in results) == 1
    assert sum(
        result.outcome is DisposalOutcome.ALREADY_EXECUTED for result in results
    ) == 7


def test_expired_plan_is_blocked_before_mutation() -> None:
    target = Harness(allow_mutations=True)
    plan = target.approved_plan()
    target.now = NOW + timedelta(minutes=16)
    result = execute(target, plan.plan_id)
    assert result.outcome is DisposalOutcome.BLOCKED
    assert result.reason == "plan_expired"
    assert target.source.has_subject(target.subject) is True
    assert target.coordinator.get(
        plan.plan_id,
        organization_id="tenant-a",
    ).status is DisposalPlanStatus.EXPIRED


def test_new_legal_hold_blocks_during_revalidation() -> None:
    target = Harness(allow_mutations=True)
    plan = target.approved_plan()
    target.holds.add(
        LegalHold(
            hold_id="hold-new-litigation",
            organization_id="tenant-a",
            record_id="session.operational_history",
            reason_code="legal.proceeding",
            approved_by_hash=APPROVAL_HASH,
            active_from=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(days=30),
            subject_hash=target.candidate().subject_hash,
        )
    )
    result = execute(target, plan.plan_id)
    assert result.outcome is DisposalOutcome.BLOCKED
    assert result.reason == "revalidation_legal_hold"
    assert target.source.delete_calls == 0


def test_policy_version_change_blocks_existing_plan() -> None:
    target = Harness(allow_mutations=True)
    plan = target.approved_plan()
    target.policies.register(
        retention_rule(
            rule_id="rule.session.retention-v2",
            version=2,
            retention_period=timedelta(days=35),
        )
    )
    result = execute(target, plan.plan_id)
    assert result.outcome is DisposalOutcome.BLOCKED
    assert result.reason == "policy_changed"
    assert target.source.delete_calls == 0


@pytest.mark.parametrize(
    "action",
    (LifecycleAction.ANONYMIZE, LifecycleAction.BLOCK),
)
def test_unsupported_adapter_action_requires_manual_work(
    action: LifecycleAction,
) -> None:
    target = Harness(allow_mutations=True, action=action)
    plan = target.approved_plan()
    result = execute(target, plan.plan_id)
    assert result.outcome is DisposalOutcome.MANUAL_ACTION_REQUIRED
    assert result.reason == f"adapter_required_{action.value}"
    assert target.source.has_subject(target.subject) is True


def test_execution_requires_execute_scope() -> None:
    target = Harness()
    plan = target.approved_plan()
    with pytest.raises(PermissionError, match="escopo"):
        target.coordinator.execute(
            officer(scopes=("privacy.retention.approve",)),
            plan.plan_id,
            confirmation=f"EXECUTAR {plan.plan_id}",
        )


def test_get_is_tenant_isolated() -> None:
    target = Harness()
    plan = target.coordinator.create_plan(target.candidate())
    with pytest.raises(PermissionError, match="outra organização"):
        target.coordinator.get(plan.plan_id, organization_id="tenant-b")


def test_disposal_audit_is_bounded_and_metadata_only() -> None:
    target = Harness(max_audit=2)
    plan = target.approved_plan()
    execute(target, plan.plan_id)
    events = target.audit.list_events()
    assert len(events) == 2
    assert events[-1].action is DisposalAuditAction.EXECUTION_PLANNED
    assert target.subject not in repr(events)
    assert "ada@example.test" not in repr(events)


def test_disposal_audit_filters_organization() -> None:
    target = Harness()
    target.coordinator.create_plan(target.candidate())
    assert len(target.audit.list_events(organization_id="tenant-a")) == 1
    assert target.audit.list_events(organization_id="tenant-b") == ()
