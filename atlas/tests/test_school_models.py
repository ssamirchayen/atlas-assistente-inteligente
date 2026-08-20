from __future__ import annotations

from datetime import datetime, timezone

import pytest

from atlas.school import (
    ApprovedTemplate,
    OptInStatus,
    SchoolLead,
    SchoolSeller,
)


def test_granted_opt_in_requires_evidence() -> None:
    with pytest.raises(ValueError, match="opt-in"):
        SchoolLead(
            lead_id="lead-1",
            name="Ana",
            phone_e164="+5592999990001",
            offering="Radiologia",
            opt_in=OptInStatus.GRANTED,
        )


def test_lead_masks_phone_and_hashes_destination() -> None:
    lead = SchoolLead(
        lead_id="lead-1",
        name="Ana",
        phone_e164="+5592999990001",
        offering="Radiologia",
        opt_in=OptInStatus.GRANTED,
        opt_in_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        opt_in_source="formulario_site",
    )

    assert lead.contact_allowed is True
    assert lead.masked_phone == "***0001"
    assert lead.phone_e164 not in lead.destination_hash
    assert len(lead.destination_hash) == 64


def test_phone_must_use_e164_format() -> None:
    with pytest.raises(ValueError, match="E.164"):
        SchoolLead(
            lead_id="lead-1",
            name="Ana",
            phone_e164="92999990001",
            offering="Radiologia",
        )


def test_seller_requires_official_phone_number_id() -> None:
    with pytest.raises(ValueError, match="phone_number_id"):
        SchoolSeller(
            seller_id="seller-1",
            name="Carlos",
            phone_number_id="whatsapp-web",
        )


def test_template_parameters_are_explicit_and_unique() -> None:
    template = ApprovedTemplate(
        name="school_lead_followup",
        parameter_names=("nome", "curso"),
    )

    assert template.name == "school_lead_followup"
    assert template.language_code == "pt_BR"

    with pytest.raises(ValueError, match="únicos"):
        ApprovedTemplate(
            name="duplicado",
            parameter_names=("nome", "nome"),
        )
