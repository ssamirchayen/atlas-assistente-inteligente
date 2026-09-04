"""Demonstração local e sem efeitos externos do PrivacyPolicyEngine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from atlas.privacy import (
    ConsentRegistry,
    DataCategory,
    DataMinimizer,
    DataTreatmentRequest,
    DeclaredLegalBasis,
    InMemoryPrivacyAuditTrail,
    PolicyStatus,
    PrivacyAction,
    PrivacyPolicy,
    PrivacyPolicyEngine,
    PrivacyPolicyRegistry,
    PrivacyPrincipal,
    Pseudonymizer,
    build_default_privacy_inventory,
)


def main() -> int:
    now = datetime.now(timezone.utc)
    pseudonymizer = Pseudonymizer(
        b"atlas-local-pilot-only-secret-key-32-bytes"
    )
    consents = ConsentRegistry(pseudonymizer, clock=lambda: now)
    audit = InMemoryPrivacyAuditTrail(max_events=10, clock=lambda: now)
    policy = PrivacyPolicy(
        policy_id="pilot.memory.preference",
        organization_id="pilot-company",
        record_id="memory.long_term_and_embeddings",
        purpose="remember.preference",
        status=PolicyStatus.ACTIVE,
        allowed_actions=(PrivacyAction.READ,),
        allowed_roles=("privacy-operator",),
        required_scopes=("memory.read",),
        allowed_legal_bases=(
            DeclaredLegalBasis.SENSITIVE_SPECIFIC_CONSENT,
        ),
        allowed_categories=(DataCategory.CONVERSATION,),
        allowed_fields=("content", "source"),
        masked_fields=("content",),
        pseudonymized_fields=("source",),
        allow_sensitive_processing=True,
        approved_by_hash=hashlib.sha256(b"pilot-controller").hexdigest(),
        approved_at=now,
    )
    engine = PrivacyPolicyEngine(
        inventory=build_default_privacy_inventory(),
        policies=PrivacyPolicyRegistry((policy,)),
        consents=consents,
        minimizer=DataMinimizer(pseudonymizer),
        audit=audit,
        principal_pseudonymizer=lambda organization, principal: (
            pseudonymizer.pseudonymize(
                principal,
                namespace=f"principal:{organization}",
            )
        ),
    )
    receipt = consents.grant(
        organization_id="pilot-company",
        subject_id="pilot-subject",
        record_id="memory.long_term_and_embeddings",
        purpose="remember.preference",
        categories=(DataCategory.CONVERSATION,),
        evidence="Pilot consent screen accepted",
        granted_by="pilot-controller",
        expires_at=now + timedelta(minutes=10),
    )
    principal = PrivacyPrincipal(
        principal_id="pilot-operator",
        organization_id="pilot-company",
        roles=("privacy-operator",),
        scopes=("memory.read",),
    )
    request = DataTreatmentRequest(
        organization_id="pilot-company",
        record_id="memory.long_term_and_embeddings",
        purpose="remember.preference",
        action=PrivacyAction.READ,
        legal_basis=DeclaredLegalBasis.SENSITIVE_SPECIFIC_CONSENT,
        categories=(DataCategory.CONVERSATION,),
        fields=("content", "source"),
        subject_id="pilot-subject",
        consent_receipt_id=receipt.receipt_id,
    )

    allowed = engine.authorize(principal, request)
    minimized = engine.minimize(
        allowed,
        {
            "content": "conteúdo fictício 1234",
            "source": "dispositivo-ficticio",
            "internal_debug": "campo removido",
        },
    )
    consents.revoke(
        receipt.receipt_id,
        organization_id="pilot-company",
        revoked_by="pilot-controller",
    )
    denied = engine.authorize(principal, request)

    print("ATLAS — PrivacyPolicyEngine (piloto local)")
    print(f"Autorização com consentimento ativo: {allowed.allowed}")
    print(f"Campos entregues após minimização: {len(minimized.data)}")
    print(f"Campos descartados: {len(minimized.dropped_fields)}")
    print(f"Autorização após revogação: {denied.allowed}")
    print(f"Motivo do bloqueio: {denied.reason.value}")
    print(f"Eventos de auditoria em memória: {len(audit.list_events())}")
    print("Nenhum dado real, arquivo, rede ou ação externa foi utilizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
