"""Piloto escolar: CRM, filas e WhatsApp Business oficial."""

from atlas.school.crm import InMemorySchoolCRM, SchoolCRM
from atlas.school.factory import (
    build_school_connector_guard,
    build_school_outreach_service,
    build_school_principal,
    build_whatsapp_client,
)
from atlas.school.models import (
    ApprovedTemplate,
    DeliveryStatus,
    LeadStatus,
    LeadSummary,
    MessageDelivery,
    OptInStatus,
    PendingApproval,
    SchoolLead,
    SchoolSeller,
)
from atlas.school.routing import SchoolLeadRouter
from atlas.school.service import SchoolOutreachService
from atlas.school.whatsapp import (
    DryRunWhatsAppClient,
    MetaWhatsAppClient,
    WhatsAppClientError,
    WhatsAppTemplateClient,
)

__all__ = [
    "ApprovedTemplate",
    "DeliveryStatus",
    "DryRunWhatsAppClient",
    "InMemorySchoolCRM",
    "LeadStatus",
    "LeadSummary",
    "MessageDelivery",
    "MetaWhatsAppClient",
    "OptInStatus",
    "PendingApproval",
    "SchoolCRM",
    "SchoolLead",
    "SchoolLeadRouter",
    "SchoolOutreachService",
    "SchoolSeller",
    "WhatsAppClientError",
    "WhatsAppTemplateClient",
    "build_school_connector_guard",
    "build_school_outreach_service",
    "build_school_principal",
    "build_whatsapp_client",
]
