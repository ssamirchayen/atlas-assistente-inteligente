"""Base segura e extensível para integrações externas do Atlas."""

from atlas.connectors.audit import (
    ConnectorAuditRecord,
    ConnectorAuditTrail,
    InMemoryConnectorAuditTrail,
    NullConnectorAuditTrail,
)
from atlas.connectors.guard import ConnectorGuard
from atlas.connectors.models import (
    ConnectorAuthorization,
    ConnectorCapability,
    ConnectorDecision,
    ConnectorManifest,
    ConnectorOperation,
    ConnectorPrincipal,
    ConnectorRisk,
)
from atlas.connectors.registry import ConnectorRegistry

__all__ = [
    "ConnectorAuditRecord",
    "ConnectorAuditTrail",
    "ConnectorAuthorization",
    "ConnectorCapability",
    "ConnectorDecision",
    "ConnectorGuard",
    "ConnectorManifest",
    "ConnectorOperation",
    "ConnectorPrincipal",
    "ConnectorRegistry",
    "ConnectorRisk",
    "InMemoryConnectorAuditTrail",
    "NullConnectorAuditTrail",
]
