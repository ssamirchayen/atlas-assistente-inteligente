from __future__ import annotations

from .business_lab import BusinessLabConnector
from .manager import IntegrationManager
from .nexyra_crm import NexyraConnector
from .registry import ConnectorRegistry, registry


def register_default_connectors() -> None:
    if not registry.has("business_lab"):
        registry.register(BusinessLabConnector())
    if not registry.has("nexyra_crm"):
        registry.register(NexyraConnector())


__all__ = [
    "BusinessLabConnector",
    "ConnectorRegistry",
    "IntegrationManager",
    "NexyraConnector",
    "register_default_connectors",
    "registry",
]
