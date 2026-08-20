"""Composição segura do piloto escolar e da WhatsApp Business."""

from __future__ import annotations

from atlas.connectors import (
    ConnectorCapability,
    ConnectorGuard,
    ConnectorManifest,
    ConnectorPrincipal,
    ConnectorRegistry,
    ConnectorRisk,
)
from atlas.core.config import (
    USER_NAME,
    WHATSAPP_ACCESS_TOKEN,
    WHATSAPP_DRY_RUN,
    WHATSAPP_GRAPH_API_VERSION,
    WHATSAPP_MAX_BATCH_SIZE,
    WHATSAPP_OPERATIONS_PER_MINUTE,
    WHATSAPP_TIMEOUT,
)
from atlas.school.crm import SchoolCRM
from atlas.school.models import ApprovedTemplate
from atlas.school.service import SchoolOutreachService
from atlas.school.whatsapp import (
    DryRunWhatsAppClient,
    MetaWhatsAppClient,
    WhatsAppTemplateClient,
)


def build_school_connector_guard() -> ConnectorGuard:
    """Registra leitura do CRM e escritas que exigem confirmação."""

    registry = ConnectorRegistry(
        (
            ConnectorManifest(
                connector_id="school.crm",
                display_name="CRM escolar",
                description="Fila e distribuição de leads da escola.",
                capabilities=(
                    ConnectorCapability(
                        name="read_leads",
                        required_scope="crm:leads:read",
                        risk=ConnectorRisk.READ_ONLY,
                    ),
                    ConnectorCapability(
                        name="assign_lead",
                        required_scope="crm:leads:assign",
                        risk=ConnectorRisk.EXTERNAL_WRITE,
                    ),
                ),
                max_batch_size=WHATSAPP_MAX_BATCH_SIZE,
                operations_per_minute=60,
            ),
            ConnectorManifest(
                connector_id="whatsapp.business",
                display_name="WhatsApp Business Platform",
                description=(
                    "Templates oficiais enviados por números corporativos."
                ),
                capabilities=(
                    ConnectorCapability(
                        name="send_template",
                        required_scope="whatsapp:messages:send",
                        risk=ConnectorRisk.EXTERNAL_WRITE,
                    ),
                ),
                max_batch_size=WHATSAPP_MAX_BATCH_SIZE,
                operations_per_minute=WHATSAPP_OPERATIONS_PER_MINUTE,
            ),
        )
    )
    return ConnectorGuard(registry)


def build_school_principal() -> ConnectorPrincipal:
    """Operador local com os escopos mínimos desta etapa."""

    return ConnectorPrincipal(
        principal_id=USER_NAME,
        role="school_operator",
        scopes=frozenset(
            {
                "crm:leads:read",
                "crm:leads:assign",
                "whatsapp:messages:send",
            }
        ),
    )


def build_whatsapp_client() -> WhatsAppTemplateClient:
    """Mantém dry-run por padrão; envio real exige configuração explícita."""

    if WHATSAPP_DRY_RUN:
        return DryRunWhatsAppClient()

    if not WHATSAPP_ACCESS_TOKEN:
        raise RuntimeError(
            "ATLAS_WHATSAPP_ACCESS_TOKEN é obrigatório fora do dry-run."
        )

    return MetaWhatsAppClient(
        access_token=WHATSAPP_ACCESS_TOKEN,
        graph_version=WHATSAPP_GRAPH_API_VERSION,
        timeout=WHATSAPP_TIMEOUT,
    )


def build_school_outreach_service(
    *,
    crm: SchoolCRM,
    approved_templates: tuple[ApprovedTemplate, ...],
    whatsapp: WhatsAppTemplateClient | None = None,
) -> SchoolOutreachService:
    return SchoolOutreachService(
        guard=build_school_connector_guard(),
        crm=crm,
        whatsapp=whatsapp or build_whatsapp_client(),
        approved_templates=approved_templates,
    )
