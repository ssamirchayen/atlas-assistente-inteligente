"""Piloto local e seguro da Sprint 24 — Etapa 4."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from atlas.privacy.disposal import DisposalCoordinator, InMemoryDisposalAuditTrail
from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import DeclaredLegalBasis, PrivacyPrincipal
from atlas.privacy.retention import (
    InMemoryRetentionAuditTrail,
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


NOW = datetime.now(timezone.utc)
SECRET = b"atlas-retention-pilot-local-key-32-bytes"


def officer(principal_id: str) -> PrivacyPrincipal:
    return PrivacyPrincipal(
        principal_id=principal_id,
        organization_id="demo-company",
        roles=("privacy-officer",),
        scopes=(
            "privacy.retention.approve",
            "privacy.retention.execute",
        ),
    )


def main() -> None:
    pseudonymizer = Pseudonymizer(SECRET)
    subject = pseudonymizer.pseudonymize(
        "fictitious-subject",
        namespace="rights:demo-company:subject",
    )
    source = InMemorySubjectDataSource(
        source_id="demo-session-store",
        organization_id="demo-company",
        record_id="session.operational_history",
        categories=(DataCategory.IDENTIFICATION,),
        fields=("display_name",),
        legal_basis=DeclaredLegalBasis.LEGAL_OBLIGATION,
    )
    source.put(subject, {"display_name": "Pessoa Fictícia"})
    policy = RetentionRule(
        rule_id="rule.demo.session",
        organization_id="demo-company",
        record_id="session.operational_history",
        status=RetentionRuleStatus.ACTIVE,
        trigger=RetentionTrigger.CREATED_AT,
        retention_period=timedelta(days=30),
        grace_period=timedelta(days=5),
        action=LifecycleAction.DELETE,
        version=1,
        processor_ids=("processor.demo",),
        approved_by_hash=hashlib.sha256(b"demo-approval").hexdigest(),
        approved_at=NOW,
    )
    retention_audit = InMemoryRetentionAuditTrail(clock=lambda: NOW)
    engine = RetentionEngine(
        policies=RetentionPolicyRegistry((policy,)),
        legal_holds=LegalHoldRegistry(),
        audit=retention_audit,
        clock=lambda: NOW,
    )
    candidate = RetentionCandidate(
        candidate_id="candidate-demo-session",
        organization_id="demo-company",
        source_id=source.source_id,
        record_id=source.record_id,
        subject_pseudonym=subject,
        created_at=NOW - timedelta(days=60),
    )
    disposal_audit = InMemoryDisposalAuditTrail(clock=lambda: NOW)
    coordinator = DisposalCoordinator(
        retention_engine=engine,
        pseudonymizer=pseudonymizer,
        sources=(source,),
        audit=disposal_audit,
        clock=lambda: NOW,
    )
    plan = coordinator.create_plan(candidate)
    coordinator.approve(
        officer("officer-a"),
        plan.plan_id,
        confirmation=f"APROVAR {plan.plan_id}",
    )
    plan = coordinator.approve(
        officer("officer-b"),
        plan.plan_id,
        confirmation=f"APROVAR {plan.plan_id}",
    )
    result = coordinator.execute(
        officer("officer-a"),
        plan.plan_id,
        confirmation=f"EXECUTAR {plan.plan_id}",
    )

    print("Sprint 24 — Etapa 4: retenção e descarte verificável")
    print(f"Decisão: {engine.evaluate(candidate).outcome.value}")
    print(f"Plano: {plan.status.value}; registros: {plan.record_count}")
    print(f"Resultado: {result.outcome.value}; motivo: {result.reason}")
    print(f"Auditoria de retenção: {len(retention_audit.list_events())} evento(s)")
    print(f"Auditoria de descarte: {len(disposal_audit.list_events())} evento(s)")
    print("Registro fictício preservado: " + str(source.has_subject(subject)))
    print("Nenhum dado foi excluído; o piloto usa dry-run por padrão.")


if __name__ == "__main__":
    main()
