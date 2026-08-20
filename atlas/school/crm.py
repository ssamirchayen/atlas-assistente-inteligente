"""Contrato de CRM escolar e implementação local para o piloto."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from threading import RLock
from typing import Protocol

from atlas.school.models import (
    LeadStatus,
    MessageDelivery,
    SchoolLead,
    SchoolSeller,
)


class SchoolCRM(Protocol):
    """Superfície que cada sistema escolar específico deverá adaptar."""

    def get_lead(self, lead_id: str) -> SchoolLead | None: ...

    def list_leads(self) -> tuple[SchoolLead, ...]: ...

    def get_seller(self, seller_id: str) -> SchoolSeller | None: ...

    def list_sellers(self) -> tuple[SchoolSeller, ...]: ...

    def assign_lead(self, lead_id: str, seller_id: str) -> SchoolLead: ...

    def mark_contacted(self, lead_id: str) -> SchoolLead: ...

    def record_delivery(self, delivery: MessageDelivery) -> None: ...


class InMemorySchoolCRM:
    """CRM determinístico usado apenas por testes e pilotos sem dados reais."""

    def __init__(
        self,
        *,
        leads: Iterable[SchoolLead] = (),
        sellers: Iterable[SchoolSeller] = (),
    ) -> None:
        lead_items = tuple(leads)
        seller_items = tuple(sellers)
        self._leads = {lead.lead_id: lead for lead in lead_items}
        self._sellers = {
            seller.seller_id: seller for seller in seller_items
        }
        self._deliveries: list[MessageDelivery] = []
        self._lock = RLock()

        if len(self._leads) != len(lead_items):
            raise ValueError("Os identificadores dos leads devem ser únicos.")
        if len(self._sellers) != len(seller_items):
            raise ValueError(
                "Os identificadores dos vendedores devem ser únicos."
            )

    def get_lead(self, lead_id: str) -> SchoolLead | None:
        with self._lock:
            return self._leads.get(lead_id)

    def list_leads(self) -> tuple[SchoolLead, ...]:
        with self._lock:
            return tuple(
                self._leads[key] for key in sorted(self._leads)
            )

    def get_seller(self, seller_id: str) -> SchoolSeller | None:
        with self._lock:
            return self._sellers.get(seller_id)

    def list_sellers(self) -> tuple[SchoolSeller, ...]:
        with self._lock:
            return tuple(
                self._sellers[key] for key in sorted(self._sellers)
            )

    def assign_lead(self, lead_id: str, seller_id: str) -> SchoolLead:
        with self._lock:
            lead = self._required_lead(lead_id)
            seller = self._sellers.get(seller_id)

            if seller is None or not seller.active:
                raise ValueError("O vendedor não existe ou está inativo.")

            updated = replace(
                lead,
                assigned_seller_id=seller_id,
                status=LeadStatus.ASSIGNED,
            )
            self._leads[lead_id] = updated
            return updated

    def mark_contacted(self, lead_id: str) -> SchoolLead:
        with self._lock:
            lead = self._required_lead(lead_id)
            updated = replace(lead, status=LeadStatus.CONTACTED)
            self._leads[lead_id] = updated
            return updated

    def record_delivery(self, delivery: MessageDelivery) -> None:
        with self._lock:
            self._deliveries.append(delivery)

    def list_deliveries(self) -> tuple[MessageDelivery, ...]:
        with self._lock:
            return tuple(self._deliveries)

    def _required_lead(self, lead_id: str) -> SchoolLead:
        lead = self._leads.get(lead_id)

        if lead is None:
            raise ValueError("Lead não encontrado no CRM escolar.")

        return lead
