"""Piloto sem rede da Sprint 24 — Etapa 5."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from atlas.privacy.catalog import build_default_privacy_inventory
from atlas.privacy.impact import (
    ImpactAssessmentService,
    ImpactRiskScenario,
    InMemoryImpactAuditTrail,
)
from atlas.privacy.incidents import (
    CommunicationFacts,
    IncidentResponseService,
    InMemoryIncidentAuditTrail,
    SecurityProperty,
)
from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import PrivacyPrincipal


NOW = datetime.now(timezone.utc)
SECRET = b"atlas-governance-pilot-local-key-32-bytes"


def officer(principal_id: str) -> PrivacyPrincipal:
    return PrivacyPrincipal(
        principal_id=principal_id,
        organization_id="demo-company",
        roles=("privacy-officer", "incident-responder"),
        scopes=(
            "privacy.incident.confirm",
            "privacy.incident.notify",
            "privacy.ripd.approve",
        ),
    )


def run_incident(pseudonymizer: Pseudonymizer) -> None:
    audit = InMemoryIncidentAuditTrail(clock=lambda: NOW)
    service = IncidentResponseService(
        pseudonymizer=pseudonymizer,
        audit=audit,
        clock=lambda: NOW,
    )
    incident = service.report(
        organization_id="demo-company",
        detected_at=NOW,
        record_ids=("school.crm_leads",),
        categories=(DataCategory.CONTACT,),
        security_properties=(SecurityProperty.CONFIDENTIALITY,),
        affected_subject_count=2,
        involves_vulnerable_group=True,
        effective_encryption=False,
        potential_impacts=("identity.fraud",),
    )
    service.confirm(
        officer("officer-a"),
        incident.incident_id,
        confirmation=f"CONFIRMAR {incident.incident_id}",
    )
    assessment = service.assess(
        incident.incident_id,
        organization_id="demo-company",
    )
    plan = service.prepare_communication(
        incident.incident_id,
        organization_id="demo-company",
        facts=CommunicationFacts(
            data_nature_documented=True,
            affected_subjects_documented=True,
            security_measures_documented=True,
            risks_documented=True,
            mitigation_documented=True,
            awareness_date_documented=True,
            controller_contact_documented=True,
        ),
    )
    for name in ("officer-a", "officer-b"):
        plan = service.approve_communication(
            officer(name),
            plan.plan_id,
            confirmation=f"APROVAR {plan.plan_id}",
        )
    tasks = service.notification_tasks(
        plan.plan_id,
        organization_id="demo-company",
    )
    receipt = service.record_manual_submission(
        officer("officer-a"),
        plan.plan_id,
        confirmation=f"REGISTRAR {plan.plan_id}",
        authority_evidence_digest=hashlib.sha256(b"demo-anpd-proof").hexdigest(),
        subjects_evidence_digest=hashlib.sha256(b"demo-subject-proof").hexdigest(),
    )
    print(f"Incidente: {assessment.conclusion.value}")
    print(f"Plano: {plan.status.value}; tarefas manuais: {len(tasks)}")
    print(f"Comprovante local registrado: {bool(receipt.receipt_id)}")
    print(f"Auditoria do incidente: {len(audit.list_events())} evento(s)")


def run_impact(pseudonymizer: Pseudonymizer) -> None:
    audit = InMemoryImpactAuditTrail(clock=lambda: NOW)
    service = ImpactAssessmentService(
        inventory=build_default_privacy_inventory(),
        pseudonymizer=pseudonymizer,
        audit=audit,
        clock=lambda: NOW,
    )
    assessment = service.create(
        organization_id="demo-company",
        purpose_code="evaluate.school.crm",
        record_ids=("school.crm_leads",),
        necessity_codes=("minimum.fields",),
        proportionality_codes=("human.review",),
        context_codes=("school.sales",),
        safeguards=("access.control", "dry.run"),
        risks=(
            ImpactRiskScenario(
                scenario_id="risk.unauthorized_access",
                likelihood=4,
                impact=4,
                controls=("access.control",),
                residual_likelihood=1,
                residual_impact=2,
            ),
        ),
    )
    evaluation = service.evaluate(
        assessment.assessment_id,
        organization_id="demo-company",
    )
    for name in ("officer-a", "officer-b"):
        service.approve(
            officer(name),
            assessment.assessment_id,
            confirmation=f"APROVAR {assessment.assessment_id}",
        )
    report = service.generate_report(
        assessment.assessment_id,
        organization_id="demo-company",
    )
    print(f"RIPD pronto: {evaluation.ready_for_approval}")
    print(f"Risco residual: {report.highest_residual_risk.value}")
    print(f"Conformidade jurídica automática: {report.legal_conformity_declared}")
    print(f"Auditoria do RIPD: {len(audit.list_events())} evento(s)")


def main() -> None:
    print("Sprint 24 — Etapa 5: incidentes e RIPD")
    pseudonymizer = Pseudonymizer(SECRET)
    run_incident(pseudonymizer)
    run_impact(pseudonymizer)
    print("Nenhuma comunicação foi enviada e nenhum dado real foi acessado.")


if __name__ == "__main__":
    main()
