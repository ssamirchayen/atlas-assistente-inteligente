from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from atlas.privacy.retention import (
    InMemoryRetentionAuditTrail,
    LegalHold,
    LegalHoldRegistry,
    LifecycleAction,
    RetentionCandidate,
    RetentionEngine,
    RetentionOutcome,
    RetentionPolicyRegistry,
    RetentionReason,
    RetentionRule,
    RetentionRuleStatus,
    RetentionTrigger,
)


NOW = datetime(2026, 2, 3, 10, tzinfo=timezone.utc)
APPROVAL_HASH = hashlib.sha256(b"retention-approval").hexdigest()
SUBJECT = "psn_" + hashlib.sha256(b"subject").hexdigest()


def rule(**changes: object) -> RetentionRule:
    values: dict[str, object] = {
        "rule_id": "rule.session.retention",
        "organization_id": "tenant-a",
        "record_id": "session.operational_history",
        "status": RetentionRuleStatus.ACTIVE,
        "trigger": RetentionTrigger.CREATED_AT,
        "retention_period": timedelta(days=30),
        "grace_period": timedelta(days=5),
        "action": LifecycleAction.DELETE,
        "version": 1,
        "processor_ids": ("processor.archive",),
        "approved_by_hash": APPROVAL_HASH,
        "approved_at": NOW,
    }
    values.update(changes)
    return RetentionRule(**values)


def candidate(**changes: object) -> RetentionCandidate:
    values: dict[str, object] = {
        "candidate_id": "candidate-session-001",
        "organization_id": "tenant-a",
        "source_id": "session-store",
        "record_id": "session.operational_history",
        "subject_pseudonym": SUBJECT,
        "created_at": NOW - timedelta(days=60),
        "last_activity_at": NOW - timedelta(days=40),
        "purpose_completed_at": NOW - timedelta(days=35),
        "consent_revoked_at": NOW - timedelta(days=10),
    }
    values.update(changes)
    return RetentionCandidate(**values)


class Harness:
    def __init__(
        self,
        *,
        rules: tuple[RetentionRule, ...] = (),
        holds: tuple[LegalHold, ...] = (),
        max_events: int = 1000,
    ) -> None:
        self.now = NOW
        self.policies = RetentionPolicyRegistry(rules)
        self.holds = LegalHoldRegistry(holds)
        self.audit = InMemoryRetentionAuditTrail(
            max_events=max_events,
            clock=lambda: self.now,
        )
        self.engine = RetentionEngine(
            policies=self.policies,
            legal_holds=self.holds,
            audit=self.audit,
            clock=lambda: self.now,
        )


def hold(**changes: object) -> LegalHold:
    values: dict[str, object] = {
        "hold_id": "hold-litigation-001",
        "organization_id": "tenant-a",
        "record_id": "session.operational_history",
        "reason_code": "legal.proceeding",
        "approved_by_hash": APPROVAL_HASH,
        "active_from": NOW - timedelta(days=1),
        "expires_at": NOW + timedelta(days=30),
        "subject_hash": candidate().subject_hash,
    }
    values.update(changes)
    return LegalHold(**values)


def test_active_rule_requires_approval() -> None:
    with pytest.raises(ValueError, match="aprovação"):
        rule(approved_by_hash=None, approved_at=None)


@pytest.mark.parametrize(
    "changes",
    (
        {"retention_period": timedelta(0)},
        {"retention_period": timedelta(days=36_526)},
        {"grace_period": timedelta(seconds=-1)},
        {"grace_period": timedelta(days=366)},
        {"version": 0},
    ),
)
def test_rule_rejects_unsafe_boundaries(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        rule(**changes)


def test_rule_rejects_duplicate_processors() -> None:
    with pytest.raises(ValueError, match="duplicidades"):
        rule(processor_ids=("processor.crm", "processor.crm"))


def test_registry_requires_monotonic_version() -> None:
    registry = RetentionPolicyRegistry((rule(),))
    with pytest.raises(ValueError, match="versão superior"):
        registry.register(rule())
    registry.register(rule(version=2, rule_id="rule.session.retention-v2"))
    assert registry.resolve("tenant-a", "session.operational_history").version == 2


def test_registry_isolates_tenants() -> None:
    registry = RetentionPolicyRegistry((rule(),))
    assert registry.resolve("tenant-b", "session.operational_history") is None


def test_candidate_requires_pseudonym_and_hides_it_from_repr() -> None:
    item = candidate()
    assert SUBJECT not in repr(item)
    with pytest.raises(ValueError, match="subject_pseudonym"):
        candidate(subject_pseudonym="raw-subject")


def test_candidate_rejects_timestamp_before_creation() -> None:
    with pytest.raises(ValueError, match="anteceder"):
        candidate(last_activity_at=NOW - timedelta(days=61))


def test_no_policy_fails_closed() -> None:
    target = Harness()
    decision = target.engine.evaluate(candidate())
    assert decision.outcome is RetentionOutcome.BLOCKED
    assert decision.reason is RetentionReason.NO_POLICY


@pytest.mark.parametrize(
    "status",
    (RetentionRuleStatus.DRAFT, RetentionRuleStatus.SUSPENDED),
)
def test_inactive_policy_fails_closed(status: RetentionRuleStatus) -> None:
    target = Harness(rules=(rule(status=status),))
    decision = target.engine.evaluate(candidate())
    assert decision.outcome is RetentionOutcome.BLOCKED
    assert decision.reason is RetentionReason.POLICY_INACTIVE


def test_missing_policy_trigger_fails_closed() -> None:
    target = Harness(
        rules=(rule(trigger=RetentionTrigger.CONSENT_REVOKED_AT),)
    )
    decision = target.engine.evaluate(candidate(consent_revoked_at=None))
    assert decision.outcome is RetentionOutcome.BLOCKED
    assert decision.reason is RetentionReason.MISSING_TRIGGER


def test_record_before_due_date_is_kept() -> None:
    target = Harness(rules=(rule(),))
    decision = target.engine.evaluate(
        candidate(
            created_at=NOW - timedelta(days=10),
            last_activity_at=None,
            purpose_completed_at=None,
            consent_revoked_at=None,
        )
    )
    assert decision.outcome is RetentionOutcome.KEEP
    assert decision.reason is RetentionReason.NOT_DUE
    assert decision.due_at == NOW + timedelta(days=20)


def test_record_inside_grace_period_is_not_executable() -> None:
    target = Harness(rules=(rule(),))
    decision = target.engine.evaluate(
        candidate(
            created_at=NOW - timedelta(days=32),
            last_activity_at=None,
            purpose_completed_at=None,
            consent_revoked_at=None,
        )
    )
    assert decision.outcome is RetentionOutcome.GRACE_PERIOD
    assert decision.reason is RetentionReason.GRACE_PERIOD
    assert decision.executable is False


@pytest.mark.parametrize(
    ("trigger", "field_name"),
    (
        (RetentionTrigger.CREATED_AT, "created_at"),
        (RetentionTrigger.LAST_ACTIVITY_AT, "last_activity_at"),
        (RetentionTrigger.PURPOSE_COMPLETED_AT, "purpose_completed_at"),
        (RetentionTrigger.CONSENT_REVOKED_AT, "consent_revoked_at"),
    ),
)
def test_all_supported_triggers_can_reach_due(
    trigger: RetentionTrigger,
    field_name: str,
) -> None:
    target = Harness(
        rules=(rule(trigger=trigger, grace_period=timedelta(0)),)
    )
    values: dict[str, object] = {field_name: NOW - timedelta(days=31)}
    if field_name == "created_at":
        values.update(
            last_activity_at=None,
            purpose_completed_at=None,
            consent_revoked_at=None,
        )
    item = candidate(**values)
    decision = target.engine.evaluate(item)
    assert decision.outcome is RetentionOutcome.DUE
    assert decision.action is LifecycleAction.DELETE


def test_active_subject_legal_hold_blocks_disposal() -> None:
    target = Harness(rules=(rule(),), holds=(hold(),))
    decision = target.engine.evaluate(candidate())
    assert decision.outcome is RetentionOutcome.BLOCKED
    assert decision.reason is RetentionReason.LEGAL_HOLD


def test_global_record_hold_matches_any_subject() -> None:
    target = Harness(rules=(rule(),), holds=(hold(subject_hash=None),))
    assert target.engine.evaluate(candidate()).reason is RetentionReason.LEGAL_HOLD


def test_hold_for_another_tenant_or_record_does_not_match() -> None:
    other_tenant = hold(
        hold_id="hold-other-tenant",
        organization_id="tenant-b",
    )
    other_record = hold(
        hold_id="hold-other-record",
        record_id="logs.application_diagnostics",
    )
    target = Harness(rules=(rule(),), holds=(other_tenant, other_record))
    assert target.engine.evaluate(candidate()).outcome is RetentionOutcome.DUE


def test_expired_hold_does_not_block() -> None:
    target = Harness(
        rules=(rule(),),
        holds=(
            hold(
                active_from=NOW - timedelta(days=20),
                expires_at=NOW - timedelta(days=1),
            ),
        ),
    )
    assert target.engine.evaluate(candidate()).outcome is RetentionOutcome.DUE


def test_released_hold_does_not_block_and_release_is_idempotent() -> None:
    registry = LegalHoldRegistry((hold(),))
    first = registry.release(
        "hold-litigation-001",
        released_at=NOW,
        released_by_hash=APPROVAL_HASH,
    )
    second = registry.release(
        "hold-litigation-001",
        released_at=NOW + timedelta(minutes=1),
        released_by_hash=APPROVAL_HASH,
    )
    assert first == second
    target = Harness(rules=(rule(),), holds=(first,))
    assert target.engine.evaluate(candidate()).outcome is RetentionOutcome.DUE


def test_duplicate_hold_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="já existe"):
        LegalHoldRegistry((hold(), replace(hold(), reason_code="audit.review")))


def test_due_decision_preserves_rule_version_and_action() -> None:
    target = Harness(rules=(rule(version=3, action=LifecycleAction.ANONYMIZE),))
    decision = target.engine.evaluate(candidate())
    assert decision.executable is True
    assert decision.rule_id == "rule.session.retention"
    assert decision.rule_version == 3
    assert decision.action is LifecycleAction.ANONYMIZE


def test_retention_audit_is_bounded_and_contains_no_subject_value() -> None:
    target = Harness(rules=(rule(),), max_events=2)
    for index in range(3):
        target.engine.evaluate(
            candidate(candidate_id=f"candidate-session-00{index}")
        )
    events = target.audit.list_events()
    assert len(events) == 2
    assert all(event.subject_hash == candidate().subject_hash for event in events)
    assert SUBJECT not in repr(events)


def test_audit_can_filter_by_organization() -> None:
    target = Harness(rules=(rule(),))
    target.engine.evaluate(candidate())
    assert len(target.audit.list_events(organization_id="tenant-a")) == 1
    assert target.audit.list_events(organization_id="tenant-b") == ()
