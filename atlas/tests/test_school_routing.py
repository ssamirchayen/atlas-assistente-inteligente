from __future__ import annotations

from atlas.school import (
    InMemorySchoolCRM,
    LeadStatus,
    SchoolLead,
    SchoolLeadRouter,
    SchoolSeller,
)


def _seller(seller_id: str, phone_number_id: str) -> SchoolSeller:
    return SchoolSeller(
        seller_id=seller_id,
        name=seller_id,
        phone_number_id=phone_number_id,
    )


def test_router_selects_smallest_active_queue() -> None:
    crm = InMemorySchoolCRM(
        sellers=(
            _seller("seller-a", "100001"),
            _seller("seller-b", "100002"),
        ),
        leads=(
            SchoolLead(
                lead_id="lead-1",
                name="Lead 1",
                phone_e164="+5592999990001",
                offering="Curso A",
                assigned_seller_id="seller-a",
                status=LeadStatus.ASSIGNED,
            ),
        ),
    )

    assert SchoolLeadRouter(crm).select_seller().seller_id == "seller-b"


def test_router_ignores_inactive_seller() -> None:
    crm = InMemorySchoolCRM(
        sellers=(
            SchoolSeller(
                seller_id="seller-a",
                name="A",
                phone_number_id="100001",
                active=False,
            ),
            _seller("seller-b", "100002"),
        ),
    )

    assert SchoolLeadRouter(crm).select_seller().seller_id == "seller-b"
