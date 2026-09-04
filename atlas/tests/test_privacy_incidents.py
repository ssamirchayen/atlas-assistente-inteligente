from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Thread

import pytest

from atlas.privacy.incidents import (
    CommunicationFacts,
    CommunicationPlanStatus,
    IncidentAuditAction,
    IncidentResponseService,
    IncidentRiskConclusion,
    IncidentStatus,
    InMemoryIncidentAuditTrail,
    SecurityProperty,
    business_days_after,
)
from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import PrivacyPrincipal


NOW = datetime(2026, 2, 6, 10, tzinfo=timezone.utc)  # sexta-feira
SECRET = b"atlas-incident-tests-secret-at-least-32-bytes"


def principal(
    principal_id: str = "officer-a",
    *,
    organization_id: str = "tenant-a",
    roles: tuple[str, ...] = ("privacy-officer", "incident-responder"),
    scopes: tuple[str, ...] = (
        "privacy.incident.confirm",
        "privacy.incident.notify",
    ),
) -> PrivacyPrincipal:
    return PrivacyPrincipal(
        principal_id=principal_id,
        organization_id=organization_id,
        roles=roles,
        scopes=scopes,
    )


def complete_facts() -> CommunicationFacts:
    return CommunicationFacts(
        data_nature_documented=True,
        affected_subjects_documented=True,
        security_measures_documented=True,
        risks_documented=True,
        mitigation_documented=True,
        awareness_date_documented=True,
        controller_contact_documented=True,
    )


class Harness:
    def __init__(self, *, max_events: int = 1000, max_incidents: int = 1000) -> None:
        self.now = NOW
        self.audit = InMemoryIncidentAuditTrail(
            max_events=max_events,
            clock=lambda: self.now,
        )
        self.service = IncidentResponseService(
            pseudonymizer=Pseudonymizer(SECRET),
            audit=self.audit,
            max_incidents=max_incidents,
            clock=lambda: self.now,
        )

    def report(self, **changes: object):
        values: dict[str, object] = {
            "organization_id": "tenant-a",
            "detected_at": NOW,
            "record_ids": ("school.crm_leads",),
            "categories": (DataCategory.CONTACT,),
            "security_properties": (SecurityProperty.CONFIDENTIALITY,),
            "affected_subject_count": 5,
            "effective_encryption": True,
        }
        values.update(changes)
        return self.service.report(**values)

    def confirmed(self, **changes: object):
        incident = self.report(**changes)
        return self.service.confirm(
            principal(),
            incident.incident_id,
            confirmation=f"CONFIRMAR {incident.incident_id}",
        )

    def relevant(self):
        incident = self.confirmed(
            involves_sensitive_data=True,
            categories=(DataCategory.HEALTH,),
            potential_impacts=("identity.fraud",),
        )
        assessment = self.service.assess(
            incident.incident_id,
            organization_id="tenant-a",
        )
        return incident, assessment


def test_business_days_skip_weekend() -> None:
    assert business_days_after(NOW, 3) == NOW + timedelta(days=5)


def test_business_days_reject_invalid_value() -> None:
    with pytest.raises(ValueError):
        business_days_after(NOW, -1)


def test_report_stores_only_structured_metadata() -> None:
    target = Harness()
    incident = target.report()
    assert incident.status is IncidentStatus.REPORTED
    assert incident.record_ids == ("school.crm_leads",)
    assert "email@example.test" not in repr(incident)


def test_report_rejects_empty_records_or_properties() -> None:
    target = Harness()
    with pytest.raises(ValueError, match="record_ids"):
        target.report(record_ids=())
    with pytest.raises(TypeError, match="security_properties"):
        target.report(security_properties=())


def test_confirm_requires_exact_confirmation() -> None:
    target = Harness()
    incident = target.report()
    with pytest.raises(PermissionError, match="confirmação"):
        target.service.confirm(principal(), incident.incident_id, confirmation="SIM")


@pytest.mark.parametrize(
    "actor",
    (
        principal(organization_id="tenant-b"),
        principal(scopes=("privacy.incident.notify",)),
    ),
)
def test_confirm_requires_tenant_and_scope(actor: PrivacyPrincipal) -> None:
    target = Harness()
    incident = target.report()
    with pytest.raises(PermissionError):
        target.service.confirm(
            actor,
            incident.incident_id,
            confirmation=f"CONFIRMAR {incident.incident_id}",
        )


def test_confirm_is_idempotent() -> None:
    target = Harness()
    incident = target.report()
    first = target.service.confirm(
        principal(), incident.incident_id, confirmation=f"CONFIRMAR {incident.incident_id}"
    )
    second = target.service.confirm(
        principal(), incident.incident_id, confirmation=f"CONFIRMAR {incident.incident_id}"
    )
    assert first == second
    assert first.confirmed_at == NOW


def test_unconfirmed_incident_is_indeterminate() -> None:
    target = Harness()
    incident = target.report()
    assessment = target.service.assess(incident.incident_id, organization_id="tenant-a")
    assert assessment.conclusion is IncidentRiskConclusion.INDETERMINATE
    assert assessment.communication_required is None
    assert assessment.authority_due_at is None


def test_sensitive_incident_is_relevant_and_has_deadline() -> None:
    target = Harness()
    _, assessment = target.relevant()
    assert assessment.conclusion is IncidentRiskConclusion.RELEVANT
    assert assessment.communication_required is True
    assert assessment.requires_human_review is True
    assert assessment.authority_due_at == NOW + timedelta(days=5)
    assert "sensitive_data" in assessment.reason_codes


@pytest.mark.parametrize(
    "changes",
    (
        {"involves_vulnerable_group": True},
        {"large_scale": True},
        {"potential_impacts": ("financial.loss",)},
    ),
)
def test_each_high_risk_indicator_escalates(changes: dict[str, object]) -> None:
    target = Harness()
    incident = target.confirmed(**changes)
    assessment = target.service.assess(incident.incident_id, organization_id="tenant-a")
    assert assessment.conclusion is IncidentRiskConclusion.RELEVANT


def test_missing_count_or_encryption_stays_indeterminate() -> None:
    target = Harness()
    incident = target.confirmed(affected_subject_count=None, effective_encryption=None)
    assessment = target.service.assess(incident.incident_id, organization_id="tenant-a")
    assert assessment.conclusion is IncidentRiskConclusion.INDETERMINATE
    assert assessment.communication_required is None


def test_low_risk_evidence_never_auto_closes() -> None:
    target = Harness()
    incident = target.confirmed()
    assessment = target.service.assess(incident.incident_id, organization_id="tenant-a")
    assert assessment.conclusion is IncidentRiskConclusion.NOT_RELEVANT
    assert assessment.communication_required is False
    assert assessment.requires_human_review is True
    assert target.service.get(
        incident.incident_id,
        organization_id="tenant-a",
    ).status is IncidentStatus.ASSESSED


def test_communication_requires_relevant_assessment() -> None:
    target = Harness()
    incident = target.confirmed()
    target.service.assess(incident.incident_id, organization_id="tenant-a")
    with pytest.raises(PermissionError, match="não autorizou"):
        target.service.prepare_communication(
            incident.incident_id,
            organization_id="tenant-a",
            facts=complete_facts(),
        )


def test_complete_communication_has_no_supplemental_deadline() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    assert plan.preliminary is False
    assert plan.supplemental_due_at is None


def test_preliminary_communication_has_twenty_business_day_deadline() -> None:
    target = Harness()
    incident, _ = target.relevant()
    facts = replace(complete_facts(), mitigation_documented=False)
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=facts,
    )
    assert plan.preliminary is True
    assert plan.supplemental_due_at == business_days_after(NOW, 20)


def test_communication_requires_two_distinct_privacy_officers() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    first = target.service.approve_communication(
        principal("officer-a"), plan.plan_id, confirmation=f"APROVAR {plan.plan_id}"
    )
    duplicate = target.service.approve_communication(
        principal("officer-a"), plan.plan_id, confirmation=f"APROVAR {plan.plan_id}"
    )
    ready = target.service.approve_communication(
        principal("officer-b"), plan.plan_id, confirmation=f"APROVAR {plan.plan_id}"
    )
    assert first.status is CommunicationPlanStatus.PENDING_APPROVAL
    assert duplicate.approval_hashes == first.approval_hashes
    assert ready.status is CommunicationPlanStatus.READY_FOR_MANUAL_SUBMISSION


def test_communication_approval_requires_role_scope_and_confirmation() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    with pytest.raises(PermissionError):
        target.service.approve_communication(
            principal(roles=("incident-responder",)),
            plan.plan_id,
            confirmation=f"APROVAR {plan.plan_id}",
        )
    with pytest.raises(PermissionError):
        target.service.approve_communication(
            principal(scopes=("privacy.incident.confirm",)),
            plan.plan_id,
            confirmation=f"APROVAR {plan.plan_id}",
        )
    with pytest.raises(PermissionError, match="confirmação"):
        target.service.approve_communication(
            principal(), plan.plan_id, confirmation="SIM"
        )


def test_notification_tasks_are_manual_and_created_only_when_ready() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    with pytest.raises(PermissionError, match="não está pronto"):
        target.service.notification_tasks(plan.plan_id, organization_id="tenant-a")
    for actor in (principal("officer-a"), principal("officer-b")):
        target.service.approve_communication(
            actor, plan.plan_id, confirmation=f"APROVAR {plan.plan_id}"
        )
    tasks = target.service.notification_tasks(plan.plan_id, organization_id="tenant-a")
    assert {task.recipient for task in tasks} == {"anpd", "affected.data_subjects"}
    assert all(task.manual_submission_required for task in tasks)


def test_notification_tasks_are_tenant_isolated() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    for name in ("officer-a", "officer-b"):
        target.service.approve_communication(
            principal(name), plan.plan_id, confirmation=f"APROVAR {plan.plan_id}"
        )
    with pytest.raises(PermissionError, match="outra organização"):
        target.service.notification_tasks(plan.plan_id, organization_id="tenant-b")


def test_manual_submission_receipt_closes_incident_and_is_idempotent() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    for name in ("officer-a", "officer-b"):
        target.service.approve_communication(
            principal(name), plan.plan_id, confirmation=f"APROVAR {plan.plan_id}"
        )
    evidence_a = "a" * 64
    evidence_b = "b" * 64
    first = target.service.record_manual_submission(
        principal(),
        plan.plan_id,
        confirmation=f"REGISTRAR {plan.plan_id}",
        authority_evidence_digest=evidence_a,
        subjects_evidence_digest=evidence_b,
    )
    second = target.service.record_manual_submission(
        principal(),
        plan.plan_id,
        confirmation=f"REGISTRAR {plan.plan_id}",
        authority_evidence_digest=evidence_a,
        subjects_evidence_digest=evidence_b,
    )
    assert first == second
    assert target.service.get(
        incident.incident_id,
        organization_id="tenant-a",
    ).status is IncidentStatus.CLOSED
    assert evidence_a in repr(first)


def test_manual_submission_requires_ready_plan_and_valid_evidence() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    with pytest.raises(PermissionError, match="não está pronto"):
        target.service.record_manual_submission(
            principal(),
            plan.plan_id,
            confirmation=f"REGISTRAR {plan.plan_id}",
            authority_evidence_digest="a" * 64,
            subjects_evidence_digest="b" * 64,
        )
    for name in ("officer-a", "officer-b"):
        target.service.approve_communication(
            principal(name), plan.plan_id, confirmation=f"APROVAR {plan.plan_id}"
        )
    with pytest.raises(ValueError, match="digest"):
        target.service.record_manual_submission(
            principal(),
            plan.plan_id,
            confirmation=f"REGISTRAR {plan.plan_id}",
            authority_evidence_digest="invalid",
            subjects_evidence_digest="b" * 64,
        )


def test_concurrent_duplicate_approvals_count_once() -> None:
    target = Harness()
    incident, _ = target.relevant()
    plan = target.service.prepare_communication(
        incident.incident_id,
        organization_id="tenant-a",
        facts=complete_facts(),
    )
    results = []

    def approve() -> None:
        results.append(
            target.service.approve_communication(
                principal("officer-a"),
                plan.plan_id,
                confirmation=f"APROVAR {plan.plan_id}",
            )
        )

    threads = [Thread(target=approve) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(len(item.approval_hashes) == 1 for item in results)


def test_audit_is_bounded_and_contains_no_payload() -> None:
    target = Harness(max_events=2)
    incident = target.confirmed()
    target.service.assess(incident.incident_id, organization_id="tenant-a")
    events = target.audit.list_events()
    assert len(events) == 2
    assert events[-1].action is IncidentAuditAction.ASSESSED
    assert "email@example.test" not in repr(events)


def test_get_is_tenant_isolated() -> None:
    target = Harness()
    incident = target.report()
    with pytest.raises(PermissionError, match="outra organização"):
        target.service.get(incident.incident_id, organization_id="tenant-b")
