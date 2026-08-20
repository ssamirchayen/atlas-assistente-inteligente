"""Distribuição previsível de leads entre números dos vendedores."""

from __future__ import annotations

from collections import Counter

from atlas.school.crm import SchoolCRM
from atlas.school.models import LeadStatus, SchoolSeller


class SchoolLeadRouter:
    """Seleciona a menor fila ativa, com desempate estável por vendedor."""

    def __init__(self, crm: SchoolCRM) -> None:
        self._crm = crm

    def select_seller(self) -> SchoolSeller:
        sellers = tuple(
            seller for seller in self._crm.list_sellers() if seller.active
        )

        if not sellers:
            raise ValueError("Não há vendedores ativos para receber o lead.")

        open_counts = Counter(
            lead.assigned_seller_id
            for lead in self._crm.list_leads()
            if lead.assigned_seller_id
            and lead.status in {LeadStatus.ASSIGNED, LeadStatus.NEW}
        )
        eligible = tuple(
            seller
            for seller in sellers
            if open_counts[seller.seller_id] < seller.max_open_leads
        )

        if not eligible:
            raise ValueError("Todas as filas de vendedores estão lotadas.")

        return min(
            eligible,
            key=lambda seller: (
                open_counts[seller.seller_id],
                seller.seller_id,
            ),
        )
