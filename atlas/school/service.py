"""Orquestra leads, aprovação humana e envio oficial pelo WhatsApp."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from uuid import uuid4

from atlas.connectors import (
    ConnectorDecision,
    ConnectorGuard,
    ConnectorOperation,
    ConnectorPrincipal,
)
from atlas.school.crm import SchoolCRM
from atlas.school.models import (
    ApprovedTemplate,
    DeliveryStatus,
    LeadSummary,
    MessageDelivery,
    OptInStatus,
    PendingApproval,
)
from atlas.school.routing import SchoolLeadRouter
from atlas.school.whatsapp import WhatsAppTemplateClient


@dataclass(frozen=True, slots=True)
class _PendingAssignment:
    operation: ConnectorOperation
    lead_id: str
    seller_id: str


@dataclass(frozen=True, slots=True)
class _PendingMessage:
    operation: ConnectorOperation
    lead_id: str
    seller_id: str
    template: ApprovedTemplate
    body_parameters: tuple[str, ...]
    destination_hash: str
    phone_number_id: str


class SchoolOutreachService:
    """Fluxo de piloto que nunca envia sem opt-in e confirmação humana."""

    def __init__(
        self,
        *,
        guard: ConnectorGuard,
        crm: SchoolCRM,
        whatsapp: WhatsAppTemplateClient,
        approved_templates: tuple[ApprovedTemplate, ...],
    ) -> None:
        templates = {
            template.name: template for template in approved_templates
        }

        if not templates:
            raise ValueError("Ao menos um template aprovado é obrigatório.")
        if len(templates) != len(approved_templates):
            raise ValueError("Os templates aprovados devem ser únicos.")

        self._guard = guard
        self._crm = crm
        self._whatsapp = whatsapp
        self._templates = templates
        self._router = SchoolLeadRouter(crm)
        self._pending_assignments: dict[str, _PendingAssignment] = {}
        self._pending_messages: dict[str, _PendingMessage] = {}
        self._lock = RLock()

    @property
    def dry_run(self) -> bool:
        return self._whatsapp.dry_run

    def list_leads(
        self,
        principal: ConnectorPrincipal,
    ) -> tuple[LeadSummary, ...]:
        """Lista dados operacionais mascarados, nunca o telefone completo."""

        leads = self._crm.list_leads()
        operation = ConnectorOperation(
            connector_id="school.crm",
            capability="read_leads",
            parameters={"result_count": len(leads), "masked": True},
            batch_size=max(1, len(leads)),
        )
        authorization = self._guard.authorize(operation, principal)

        if not authorization.allowed:
            raise PermissionError(authorization.reason)

        return tuple(LeadSummary.from_lead(lead) for lead in leads)

    def suggest_seller(self) -> str:
        """Seleciona a menor fila sem alterar o CRM."""

        return self._router.select_seller().seller_id

    def prepare_assignment(
        self,
        *,
        lead_id: str,
        seller_id: str,
        principal: ConnectorPrincipal,
        idempotency_key: str | None = None,
    ) -> PendingApproval:
        """Prepara a escrita no CRM e solicita confirmação do operador."""

        lead = self._required_lead(lead_id)
        seller = self._required_seller(seller_id)

        if lead.assigned_seller_id == seller.seller_id:
            raise ValueError("O lead já pertence a esse vendedor.")

        operation = ConnectorOperation(
            connector_id="school.crm",
            capability="assign_lead",
            parameters={
                "lead_id": lead.lead_id,
                "seller_id": seller.seller_id,
            },
            idempotency_key=idempotency_key
            or f"assign:{lead.lead_id}:{seller.seller_id}",
        )
        authorization = self._guard.authorize(operation, principal)
        summary = (
            f"Atribuir o lead {lead.lead_id} ao vendedor "
            f"{seller.name}."
        )

        if authorization.requires_confirmation:
            token = authorization.confirmation_token

            if token is None:
                raise RuntimeError("A política não gerou confirmação.")

            with self._lock:
                self._pending_assignments[token] = _PendingAssignment(
                    operation=operation,
                    lead_id=lead.lead_id,
                    seller_id=seller.seller_id,
                )

            return PendingApproval(
                operation_id=operation.operation_id,
                summary=summary,
                allowed=False,
                reason=authorization.reason,
                confirmation_token=token,
                expires_at=authorization.confirmation_expires_at,
            )

        return PendingApproval(
            operation_id=operation.operation_id,
            summary=summary,
            allowed=False,
            reason=authorization.reason,
        )

    def confirm_assignment(
        self,
        confirmation_token: str,
        principal: ConnectorPrincipal,
    ) -> LeadSummary:
        """Consome a aprovação e somente então grava a distribuição."""

        with self._lock:
            pending = self._pending_assignments.get(confirmation_token)

        if pending is None:
            raise ValueError("A confirmação da atribuição não existe.")

        authorization = self._guard.authorize(
            pending.operation,
            principal,
            confirmation_token=confirmation_token,
        )

        if not authorization.allowed:
            raise PermissionError(authorization.reason)

        with self._lock:
            self._pending_assignments.pop(confirmation_token, None)

        lead = self._crm.assign_lead(
            pending.lead_id,
            pending.seller_id,
        )
        return LeadSummary.from_lead(lead)

    def prepare_template_message(
        self,
        *,
        lead_id: str,
        template_name: str,
        values: dict[str, str],
        principal: ConnectorPrincipal,
        idempotency_key: str | None = None,
    ) -> PendingApproval:
        """Valida consentimento e prepara um template oficial."""

        lead = self._required_lead(lead_id)

        if not lead.contact_allowed:
            if lead.opt_in is OptInStatus.UNKNOWN:
                reason = "O lead não possui prova de opt-in."
            else:
                reason = "O lead revogou ou bloqueou o contato."
            return PendingApproval(
                operation_id=uuid4().hex,
                summary=f"Contato do lead {lead.lead_id} bloqueado.",
                allowed=False,
                reason=reason,
            )

        if lead.assigned_seller_id is None:
            raise ValueError("O lead ainda não possui vendedor responsável.")

        seller = self._required_seller(lead.assigned_seller_id)
        template = self._templates.get(template_name.strip().lower())

        if template is None:
            raise ValueError("O template não está na lista aprovada.")

        normalized_values = {key.strip(): str(value).strip() for key, value in values.items()}

        if set(normalized_values) != set(template.parameter_names):
            raise ValueError("Os parâmetros não correspondem ao template.")
        if any(not value for value in normalized_values.values()):
            raise ValueError("Os valores do template não podem ser vazios.")

        ordered_values = tuple(
            normalized_values[name] for name in template.parameter_names
        )
        parameter_hash = sha256(
            "\x1f".join(ordered_values).encode("utf-8")
        ).hexdigest()
        business_key = idempotency_key or (
            f"message:{lead.lead_id}:{template.name}:{parameter_hash[:16]}"
        )
        operation = ConnectorOperation(
            connector_id="whatsapp.business",
            capability="send_template",
            parameters={
                "lead_id": lead.lead_id,
                "seller_id": seller.seller_id,
                "destination_sha256": lead.destination_hash,
                "template": template.name,
                "language": template.language_code,
                "parameter_sha256": parameter_hash,
                "opt_in_at": (
                    lead.opt_in_at.isoformat() if lead.opt_in_at else ""
                ),
            },
            idempotency_key=business_key,
        )
        authorization = self._guard.authorize(operation, principal)
        summary = (
            f"Enviar o template {template.name} ao lead {lead.lead_id} "
            f"pelo número corporativo de {seller.name}."
        )

        if authorization.requires_confirmation:
            token = authorization.confirmation_token

            if token is None:
                raise RuntimeError("A política não gerou confirmação.")

            with self._lock:
                self._pending_messages[token] = _PendingMessage(
                    operation=operation,
                    lead_id=lead.lead_id,
                    seller_id=seller.seller_id,
                    template=template,
                    body_parameters=ordered_values,
                    destination_hash=lead.destination_hash,
                    phone_number_id=seller.phone_number_id,
                )

            return PendingApproval(
                operation_id=operation.operation_id,
                summary=summary,
                allowed=False,
                reason=authorization.reason,
                confirmation_token=token,
                expires_at=authorization.confirmation_expires_at,
            )

        return PendingApproval(
            operation_id=operation.operation_id,
            summary=summary,
            allowed=False,
            reason=authorization.reason,
        )

    def confirm_template_message(
        self,
        confirmation_token: str,
        principal: ConnectorPrincipal,
    ) -> MessageDelivery:
        """Envia uma vez pelo número oficial do vendedor responsável."""

        with self._lock:
            pending = self._pending_messages.get(confirmation_token)

        if pending is None:
            raise ValueError("A confirmação da mensagem não existe.")

        lead = self._required_lead(pending.lead_id)
        seller = self._required_seller(pending.seller_id)

        if not lead.contact_allowed:
            raise PermissionError("O opt-in não permite mais este contato.")
        if lead.assigned_seller_id != seller.seller_id:
            raise PermissionError("O vendedor responsável foi alterado.")
        if lead.destination_hash != pending.destination_hash:
            raise PermissionError("O telefone do lead foi alterado.")
        if seller.phone_number_id != pending.phone_number_id:
            raise PermissionError("O número corporativo foi alterado.")

        authorization = self._guard.authorize(
            pending.operation,
            principal,
            confirmation_token=confirmation_token,
        )

        if authorization.decision is not ConnectorDecision.ALLOWED:
            raise PermissionError(authorization.reason)

        with self._lock:
            self._pending_messages.pop(confirmation_token, None)

        provider_message_id = self._whatsapp.send_template(
            phone_number_id=seller.phone_number_id,
            recipient_e164=lead.phone_e164,
            template_name=pending.template.name,
            language_code=pending.template.language_code,
            body_parameters=pending.body_parameters,
        )
        delivery = MessageDelivery(
            delivery_id=uuid4().hex,
            lead_id=lead.lead_id,
            seller_id=seller.seller_id,
            destination_hash=lead.destination_hash,
            template_name=pending.template.name,
            provider_message_id=provider_message_id,
            status=(
                DeliveryStatus.DRY_RUN
                if self._whatsapp.dry_run
                else DeliveryStatus.ACCEPTED
            ),
        )
        self._crm.record_delivery(delivery)
        self._crm.mark_contacted(lead.lead_id)
        return delivery

    def _required_lead(self, lead_id: str):
        lead = self._crm.get_lead(lead_id)

        if lead is None:
            raise ValueError("Lead não encontrado no CRM escolar.")

        return lead

    def _required_seller(self, seller_id: str):
        seller = self._crm.get_seller(seller_id)

        if seller is None or not seller.active:
            raise ValueError("O vendedor não existe ou está inativo.")

        return seller
