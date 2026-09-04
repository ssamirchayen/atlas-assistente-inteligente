"""Piloto local dos direitos dos titulares, sem efeitos externos."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from atlas.privacy import (
    ConsentRegistry,
    DataCategory,
    DataMinimizer,
    DeclaredLegalBasis,
    InMemoryPrivacyAuditTrail,
    InMemoryRightsAuditTrail,
    InMemorySubjectDataSource,
    PolicyStatus,
    PrivacyAction,
    PrivacyPolicy,
    PrivacyPolicyEngine,
    PrivacyPolicyRegistry,
    PrivacyPrincipal,
    Pseudonymizer,
    RightsSourceSelection,
    SubjectRight,
    SubjectRightsService,
    build_default_privacy_inventory,
)


def _principal(principal_id: str) -> PrivacyPrincipal:
    return PrivacyPrincipal(
        principal_id=principal_id,
        organization_id="pilot-company",
        roles=("privacy-officer",),
        scopes=("privacy.rights.review", "privacy.rights.execute"),
    )


def _verify_and_approve(
    service: SubjectRightsService,
    request_id: str,
    *,
    two_approvals: bool,
) -> None:
    challenge = service.issue_verification_challenge(
        request_id,
        organization_id="pilot-company",
    )
    service.verify_identity(
        request_id,
        organization_id="pilot-company",
        token=challenge.token,
    )
    service.approve(
        _principal("pilot-officer-a"),
        request_id,
        confirmation=f"APROVAR {request_id}",
    )
    if two_approvals:
        service.approve(
            _principal("pilot-officer-b"),
            request_id,
            confirmation=f"APROVAR {request_id}",
        )


def main() -> int:
    now = datetime.now(timezone.utc)
    pseudonymizer = Pseudonymizer(
        b"atlas-rights-pilot-only-key-at-least-32-bytes"
    )
    source = InMemorySubjectDataSource(
        source_id="pilot-session-store",
        organization_id="pilot-company",
        record_id="session.operational_history",
        categories=(DataCategory.IDENTIFICATION,),
        fields=("display_name", "preference"),
        legal_basis=DeclaredLegalBasis.LEGAL_OBLIGATION,
    )
    policy = PrivacyPolicy(
        policy_id="pilot.subject.rights",
        organization_id="pilot-company",
        record_id="session.operational_history",
        purpose="fulfill.subject_rights",
        status=PolicyStatus.ACTIVE,
        allowed_actions=(PrivacyAction.READ, PrivacyAction.DELETE),
        allowed_roles=("privacy-officer",),
        required_scopes=("privacy.rights.execute",),
        allowed_legal_bases=(DeclaredLegalBasis.LEGAL_OBLIGATION,),
        allowed_categories=(DataCategory.IDENTIFICATION,),
        allowed_fields=("display_name", "preference"),
        approved_by_hash=hashlib.sha256(b"pilot-controller").hexdigest(),
        approved_at=now,
    )
    policy_engine = PrivacyPolicyEngine(
        inventory=build_default_privacy_inventory(),
        policies=PrivacyPolicyRegistry((policy,)),
        consents=ConsentRegistry(pseudonymizer, clock=lambda: now),
        minimizer=DataMinimizer(pseudonymizer),
        audit=InMemoryPrivacyAuditTrail(clock=lambda: now),
        principal_pseudonymizer=lambda organization, principal: (
            pseudonymizer.pseudonymize(
                principal,
                namespace=f"principal:{organization}",
            )
        ),
    )
    rights_audit = InMemoryRightsAuditTrail(clock=lambda: now)
    service = SubjectRightsService(
        policy_engine=policy_engine,
        pseudonymizer=pseudonymizer,
        sources=(source,),
        audit=rights_audit,
        clock=lambda: now,
    )
    subject = service.subject_pseudonym(
        organization_id="pilot-company",
        subject_id="pilot-subject",
    )
    source.put(
        subject,
        {"display_name": "Pessoa Fictícia", "preference": "modo escuro"},
    )
    selection = RightsSourceSelection(
        source_id="pilot-session-store",
        fields=("display_name", "preference"),
    )

    access = service.submit(
        organization_id="pilot-company",
        subject_id="pilot-subject",
        right=SubjectRight.ACCESS,
        selections=(selection,),
    )
    _verify_and_approve(service, access.request_id, two_approvals=False)
    access_result = service.execute(
        _principal("pilot-officer-a"),
        access.request_id,
        confirmation=f"EXECUTAR {access.request_id}",
    )

    deletion = service.submit(
        organization_id="pilot-company",
        subject_id="pilot-subject",
        right=SubjectRight.DELETION,
        selections=(selection,),
    )
    _verify_and_approve(service, deletion.request_id, two_approvals=True)
    deletion_result = service.execute(
        _principal("pilot-officer-a"),
        deletion.request_id,
        confirmation=f"EXECUTAR {deletion.request_id}",
    )

    print("ATLAS — Direitos dos Titulares (piloto local)")
    print(f"Acesso concluído: {access_result.outcome.value}")
    print(f"Fontes incluídas: {access_result.source_count}")
    print(f"Exclusão em modo seguro: {deletion_result.outcome.value}")
    print(f"Registros planejados: {deletion_result.mutation_plans[0].record_count}")
    print(f"Dado fictício preservado: {source.has_subject(subject)}")
    print(f"Eventos de auditoria: {len(rights_audit.list_events())}")
    print("Nenhum arquivo, banco, rede ou dado real foi utilizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
