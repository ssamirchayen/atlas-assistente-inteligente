from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from atlas.connectors import ConnectorPrincipal
from atlas.school import (
    ApprovedTemplate,
    DeliveryStatus,
    DryRunWhatsAppClient,
    InMemorySchoolCRM,
    LeadStatus,
    OptInStatus,
    SchoolLead,
    SchoolOutreachService,
    SchoolSeller,
    build_school_connector_guard,
    build_school_principal,
)


def _lead(
    *,
    opt_in: OptInStatus = OptInStatus.GRANTED,
    assigned: bool = True,
) -> SchoolLead:
    return SchoolLead(
        lead_id="lead-1",
        name="Ana",
        phone_e164="+5592999990001",
        offering="Radiologia",
        opt_in=opt_in,
        opt_in_at=(
            datetime(2026, 8, 20, tzinfo=timezone.utc)
            if opt_in is OptInStatus.GRANTED
            else None
        ),
        opt_in_source=(
            "formulario_site" if opt_in is OptInStatus.GRANTED else ""
        ),
        assigned_seller_id="seller-1" if assigned else None,
        status=LeadStatus.ASSIGNED if assigned else LeadStatus.NEW,
    )


def _seller() -> SchoolSeller:
    return SchoolSeller(
        seller_id="seller-1",
        name="Carlos",
        phone_number_id="123456789012345",
    )


def _service(
    lead: SchoolLead | None = None,
) -> tuple[
    SchoolOutreachService,
    InMemorySchoolCRM,
    DryRunWhatsAppClient,
]:
    crm = InMemorySchoolCRM(
        leads=(lead or _lead(),),
        sellers=(_seller(),),
    )
    whatsapp = DryRunWhatsAppClient()
    service = SchoolOutreachService(
        guard=build_school_connector_guard(),
        crm=crm,
        whatsapp=whatsapp,
        approved_templates=(
            ApprovedTemplate(
                name="school_lead_followup",
                parameter_names=("nome", "curso"),
            ),
        ),
    )
    return service, crm, whatsapp


def test_list_leads_returns_only_masked_phone() -> None:
    service, _, _ = _service()

    summaries = service.list_leads(build_school_principal())

    assert summaries[0].masked_phone == "***0001"
    assert not hasattr(summaries[0], "phone_e164")


def test_assignment_requires_and_consumes_human_confirmation() -> None:
    service, crm, _ = _service(_lead(assigned=False))
    principal = build_school_principal()

    approval = service.prepare_assignment(
        lead_id="lead-1",
        seller_id="seller-1",
        principal=principal,
    )

    assert approval.allowed is False
    assert approval.confirmation_token is not None
    assert crm.get_lead("lead-1").assigned_seller_id is None

    summary = service.confirm_assignment(
        approval.confirmation_token,
        principal,
    )

    assert summary.assigned_seller_id == "seller-1"
    assert summary.status is LeadStatus.ASSIGNED

    with pytest.raises(ValueError, match="não existe"):
        service.confirm_assignment(approval.confirmation_token, principal)


def test_message_is_blocked_without_opt_in() -> None:
    service, _, whatsapp = _service(_lead(opt_in=OptInStatus.UNKNOWN))

    approval = service.prepare_template_message(
        lead_id="lead-1",
        template_name="school_lead_followup",
        values={"nome": "Ana", "curso": "Radiologia"},
        principal=build_school_principal(),
    )

    assert approval.confirmation_token is None
    assert "opt-in" in approval.reason
    assert whatsapp.calls == []


def test_confirmed_template_uses_sellers_official_number() -> None:
    service, crm, whatsapp = _service()
    principal = build_school_principal()

    approval = service.prepare_template_message(
        lead_id="lead-1",
        template_name="school_lead_followup",
        values={"nome": "Ana", "curso": "Radiologia"},
        principal=principal,
    )

    assert approval.confirmation_token is not None
    assert whatsapp.calls == []

    delivery = service.confirm_template_message(
        approval.confirmation_token,
        principal,
    )

    assert delivery.status is DeliveryStatus.DRY_RUN
    assert delivery.destination_hash != "+5592999990001"
    assert whatsapp.calls[0]["phone_number_id"] == "123456789012345"
    assert whatsapp.calls[0]["recipient_e164"] == "+5592999990001"
    assert crm.get_lead("lead-1").status is LeadStatus.CONTACTED
    assert crm.list_deliveries() == (delivery,)


def test_message_confirmation_belongs_to_same_principal() -> None:
    service, _, whatsapp = _service()
    principal = build_school_principal()
    approval = service.prepare_template_message(
        lead_id="lead-1",
        template_name="school_lead_followup",
        values={"nome": "Ana", "curso": "Radiologia"},
        principal=principal,
    )
    intruder = ConnectorPrincipal(
        principal_id="other-operator",
        role="school_operator",
        scopes=principal.scopes,
    )

    with pytest.raises(PermissionError, match="outro solicitante"):
        service.confirm_template_message(
            approval.confirmation_token,
            intruder,
        )

    assert whatsapp.calls == []


def test_opt_in_is_rechecked_immediately_before_send() -> None:
    service, crm, whatsapp = _service()
    principal = build_school_principal()
    approval = service.prepare_template_message(
        lead_id="lead-1",
        template_name="school_lead_followup",
        values={"nome": "Ana", "curso": "Radiologia"},
        principal=principal,
    )
    current = crm.get_lead("lead-1")
    crm._leads["lead-1"] = replace(
        current,
        opt_in=OptInStatus.REVOKED,
        opt_in_at=None,
        opt_in_source="",
    )

    with pytest.raises(PermissionError, match="opt-in"):
        service.confirm_template_message(
            approval.confirmation_token,
            principal,
        )

    assert whatsapp.calls == []


def test_duplicate_message_content_is_not_prepared_twice() -> None:
    service, _, _ = _service()
    principal = build_school_principal()
    values = {"nome": "Ana", "curso": "Radiologia"}
    first = service.prepare_template_message(
        lead_id="lead-1",
        template_name="school_lead_followup",
        values=values,
        principal=principal,
    )
    service.confirm_template_message(first.confirmation_token, principal)

    duplicate = service.prepare_template_message(
        lead_id="lead-1",
        template_name="school_lead_followup",
        values=values,
        principal=principal,
    )

    assert duplicate.confirmation_token is None
    assert "já foi autorizada" in duplicate.reason
