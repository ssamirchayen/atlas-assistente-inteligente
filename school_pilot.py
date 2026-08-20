"""Demonstração local da fila escolar; nunca envia mensagem real."""

from __future__ import annotations

from datetime import datetime, timezone

from atlas.school import (
    ApprovedTemplate,
    DryRunWhatsAppClient,
    InMemorySchoolCRM,
    OptInStatus,
    SchoolLead,
    SchoolOutreachService,
    SchoolSeller,
    build_school_connector_guard,
    build_school_principal,
)


def _confirmed(prompt: str) -> bool:
    return input(f"{prompt} Digite SIM para confirmar: ").strip() == "SIM"


def main() -> int:
    """Executa atribuição e mensagem com dados inteiramente fictícios."""

    crm = InMemorySchoolCRM(
        leads=(
            SchoolLead(
                lead_id="demo-lead-1",
                name="Lead Demonstração",
                phone_e164="+5592999990001",
                offering="Curso de Radiologia",
                opt_in=OptInStatus.GRANTED,
                opt_in_at=datetime.now(timezone.utc),
                opt_in_source="formulario_demo",
            ),
        ),
        sellers=(
            SchoolSeller(
                seller_id="vendedor-1",
                name="Vendedor Demonstração",
                phone_number_id="123456789012345",
            ),
        ),
    )
    service = SchoolOutreachService(
        guard=build_school_connector_guard(),
        crm=crm,
        whatsapp=DryRunWhatsAppClient(),
        approved_templates=(
            ApprovedTemplate(
                name="school_lead_followup",
                parameter_names=("nome", "curso"),
            ),
        ),
    )
    principal = build_school_principal()
    seller_id = service.suggest_seller()
    assignment = service.prepare_assignment(
        lead_id="demo-lead-1",
        seller_id=seller_id,
        principal=principal,
    )
    print(f"\n{assignment.summary}")

    if not _confirmed("Atribuir o lead?"):
        print("Operação cancelada. Nenhum dado foi alterado.")
        return 0

    service.confirm_assignment(
        assignment.confirmation_token,
        principal,
    )
    message = service.prepare_template_message(
        lead_id="demo-lead-1",
        template_name="school_lead_followup",
        values={
            "nome": "Lead Demonstração",
            "curso": "Curso de Radiologia",
        },
        principal=principal,
    )
    print(f"\n{message.summary}")

    if not _confirmed("Simular o envio do template?"):
        print("Operação cancelada. Nenhuma mensagem foi simulada.")
        return 0

    delivery = service.confirm_template_message(
        message.confirmation_token,
        principal,
    )
    print(
        "\nDry-run concluído. "
        f"Status: {delivery.status.value}; "
        f"ID: {delivery.provider_message_id}."
    )
    print("Nenhuma mensagem real foi enviada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
