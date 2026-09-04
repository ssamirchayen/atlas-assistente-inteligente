from __future__ import annotations

from datetime import datetime, timezone
from threading import Thread

import pytest

from atlas.privacy.catalog import build_default_privacy_inventory
from atlas.privacy.impact import (
    ImpactAssessmentService,
    ImpactAssessmentStatus,
    ImpactAuditAction,
    ImpactRiskScenario,
    InMemoryImpactAuditTrail,
    ResidualRisk,
)
from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.policy import PrivacyPrincipal


NOW = datetime(2026, 2, 3, 10, tzinfo=timezone.utc)
SECRET = b"atlas-impact-tests-secret-at-least-32-bytes"


def officer(
    principal_id: str = "officer-a",
    *,
    organization_id: str = "tenant-a",
    roles: tuple[str, ...] = ("privacy-officer",),
    scopes: tuple[str, ...] = ("privacy.ripd.approve",),
) -> PrivacyPrincipal:
    return PrivacyPrincipal(
        principal_id=principal_id,
        organization_id=organization_id,
        roles=roles,
        scopes=scopes,
    )


def low_risk(**changes: object) -> ImpactRiskScenario:
    values: dict[str, object] = {
        "scenario_id": "risk.unauthorized_access",
        "likelihood": 4,
        "impact": 4,
        "controls": ("access.control", "audit.metadata"),
        "residual_likelihood": 1,
        "residual_impact": 2,
    }
    values.update(changes)
    return ImpactRiskScenario(**values)


class Harness:
    def __init__(self, *, max_events: int = 1000) -> None:
        self.now = NOW
        self.audit = InMemoryImpactAuditTrail(
            max_events=max_events,
            clock=lambda: self.now,
        )
        self.service = ImpactAssessmentService(
            inventory=build_default_privacy_inventory(),
            pseudonymizer=Pseudonymizer(SECRET),
            audit=self.audit,
            clock=lambda: self.now,
        )

    def complete(self, **changes: object):
        values: dict[str, object] = {
            "organization_id": "tenant-a",
            "purpose_code": "evaluate.school.crm",
            "record_ids": ("school.crm_leads",),
            "necessity_codes": ("minimum.fields",),
            "proportionality_codes": ("human.review",),
            "context_codes": ("school.sales",),
            "safeguards": ("access.control", "dry.run"),
            "risks": (low_risk(),),
        }
        values.update(changes)
        return self.service.create(**values)

    def evaluated(self, **changes: object):
        assessment = self.complete(**changes)
        evaluation = self.service.evaluate(
            assessment.assessment_id,
            organization_id="tenant-a",
        )
        return assessment, evaluation


@pytest.mark.parametrize(
    ("score", "expected"),
    (
        ((1, 4), ResidualRisk.LOW),
        ((3, 3), ResidualRisk.MEDIUM),
        ((4, 4), ResidualRisk.HIGH),
        ((5, 5), ResidualRisk.CRITICAL),
    ),
)
def test_residual_risk_bands(score: tuple[int, int], expected: ResidualRisk) -> None:
    risk = low_risk(
        likelihood=5,
        impact=5,
        residual_likelihood=score[0],
        residual_impact=score[1],
    )
    assert risk.residual_risk is expected


def test_risk_rejects_invalid_scores_and_worsening_residual() -> None:
    with pytest.raises(ValueError):
        low_risk(likelihood=0)
    with pytest.raises(ValueError, match="residual"):
        low_risk(
            likelihood=1,
            impact=1,
            residual_likelihood=2,
            residual_impact=2,
        )


def test_risk_requires_declared_controls() -> None:
    with pytest.raises(ValueError, match="controls"):
        low_risk(controls=())


def test_create_rejects_unknown_inventory_record() -> None:
    target = Harness()
    with pytest.raises(KeyError, match="não inventariado"):
        target.complete(record_ids=("unknown.data",))


def test_draft_contains_codes_and_no_personal_payload() -> None:
    target = Harness()
    assessment = target.complete()
    assert assessment.status is ImpactAssessmentStatus.DRAFT
    assert assessment.record_ids == ("school.crm_leads",)
    assert "person@example.test" not in repr(assessment)


@pytest.mark.parametrize(
    ("field_name", "missing_code"),
    (
        ("necessity_codes", "missing.necessity_codes"),
        ("proportionality_codes", "missing.proportionality_codes"),
        ("context_codes", "missing.context_codes"),
        ("safeguards", "missing.safeguards"),
        ("risks", "missing.risks"),
    ),
)
def test_evaluation_lists_each_missing_section(
    field_name: str,
    missing_code: str,
) -> None:
    target = Harness()
    assessment, evaluation = target.evaluated(**{field_name: ()})
    assert assessment.status is ImpactAssessmentStatus.DRAFT
    assert missing_code in evaluation.missing_sections
    assert evaluation.ready_for_approval is False


def test_evaluation_derives_sensitive_child_and_transfer_flags() -> None:
    target = Harness()
    _, evaluation = target.evaluated(
        record_ids=("school.crm_leads", "voice.speech_recognition")
    )
    assert evaluation.includes_sensitive_processing is True
    assert evaluation.includes_children is True
    assert evaluation.includes_international_transfer is True


def test_complete_low_risk_assessment_is_ready() -> None:
    target = Harness()
    _, evaluation = target.evaluated()
    assert evaluation.highest_residual_risk is ResidualRisk.LOW
    assert evaluation.unresolved_high_risks == ()
    assert evaluation.ready_for_approval is True


def test_high_or_critical_residual_risk_blocks_approval() -> None:
    target = Harness()
    assessment, evaluation = target.evaluated(
        risks=(
            low_risk(
                likelihood=5,
                impact=5,
                residual_likelihood=4,
                residual_impact=4,
            ),
        )
    )
    assert evaluation.unresolved_high_risks == ("risk.unauthorized_access",)
    with pytest.raises(PermissionError, match="riscos altos"):
        target.service.approve(
            officer(),
            assessment.assessment_id,
            confirmation=f"APROVAR {assessment.assessment_id}",
        )


def test_approval_requires_prior_complete_evaluation() -> None:
    target = Harness()
    assessment = target.complete()
    with pytest.raises(PermissionError, match="lacunas"):
        target.service.approve(
            officer(),
            assessment.assessment_id,
            confirmation=f"APROVAR {assessment.assessment_id}",
        )


@pytest.mark.parametrize(
    "actor",
    (
        officer(organization_id="tenant-b"),
        officer(roles=("admin",)),
        officer(scopes=("privacy.ripd.read",)),
    ),
)
def test_approval_requires_tenant_role_and_scope(actor: PrivacyPrincipal) -> None:
    target = Harness()
    assessment, _ = target.evaluated()
    with pytest.raises(PermissionError):
        target.service.approve(
            actor,
            assessment.assessment_id,
            confirmation=f"APROVAR {assessment.assessment_id}",
        )


def test_approval_requires_exact_confirmation() -> None:
    target = Harness()
    assessment, _ = target.evaluated()
    with pytest.raises(PermissionError, match="confirmação"):
        target.service.approve(
            officer(),
            assessment.assessment_id,
            confirmation="SIM",
        )


def test_two_distinct_approvals_are_required() -> None:
    target = Harness()
    assessment, _ = target.evaluated()
    first = target.service.approve(
        officer("officer-a"),
        assessment.assessment_id,
        confirmation=f"APROVAR {assessment.assessment_id}",
    )
    duplicate = target.service.approve(
        officer("officer-a"),
        assessment.assessment_id,
        confirmation=f"APROVAR {assessment.assessment_id}",
    )
    second = target.service.approve(
        officer("officer-b"),
        assessment.assessment_id,
        confirmation=f"APROVAR {assessment.assessment_id}",
    )
    assert first.status is ImpactAssessmentStatus.DRAFT
    assert duplicate.approval_hashes == first.approval_hashes
    assert second.status is ImpactAssessmentStatus.APPROVED


def test_concurrent_duplicate_approval_counts_once() -> None:
    target = Harness()
    assessment, _ = target.evaluated()
    results = []

    def approve() -> None:
        results.append(
            target.service.approve(
                officer("officer-a"),
                assessment.assessment_id,
                confirmation=f"APROVAR {assessment.assessment_id}",
            )
        )

    threads = [Thread(target=approve) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(len(item.approval_hashes) == 1 for item in results)


def test_report_requires_two_approvals() -> None:
    target = Harness()
    assessment, _ = target.evaluated()
    target.service.approve(
        officer(),
        assessment.assessment_id,
        confirmation=f"APROVAR {assessment.assessment_id}",
    )
    with pytest.raises(PermissionError, match="duas pessoas"):
        target.service.generate_report(
            assessment.assessment_id,
            organization_id="tenant-a",
        )


def test_approved_report_is_metadata_only_and_no_legal_declaration() -> None:
    target = Harness()
    assessment, _ = target.evaluated()
    for name in ("officer-a", "officer-b"):
        target.service.approve(
            officer(name),
            assessment.assessment_id,
            confirmation=f"APROVAR {assessment.assessment_id}",
        )
    report = target.service.generate_report(
        assessment.assessment_id,
        organization_id="tenant-a",
    )
    assert report.record_count == 1
    assert report.highest_residual_risk is ResidualRisk.LOW
    assert report.human_approval_required is True
    assert report.legal_conformity_declared is False
    assert len(report.inventory_digest) == 64
    assert len(report.assessment_digest) == 64
    assert "person@example.test" not in repr(report)


def test_get_and_report_are_tenant_isolated() -> None:
    target = Harness()
    assessment, _ = target.evaluated()
    with pytest.raises(PermissionError, match="outra organização"):
        target.service.get(assessment.assessment_id, organization_id="tenant-b")


def test_audit_is_bounded_and_metadata_only() -> None:
    target = Harness(max_events=2)
    assessment, _ = target.evaluated()
    target.service.approve(
        officer(),
        assessment.assessment_id,
        confirmation=f"APROVAR {assessment.assessment_id}",
    )
    events = target.audit.list_events()
    assert len(events) == 2
    assert events[-1].action is ImpactAuditAction.APPROVED
    assert "person@example.test" not in repr(events)
