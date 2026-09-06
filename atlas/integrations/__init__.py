from __future__ import annotations

from .business_lab import BusinessLabConnector
from .manager import IntegrationManager
from .registry import ConnectorRegistry, registry


def register_default_connectors() -> None:
    if not registry.has("business_lab"):
        registry.register(BusinessLabConnector())


__all__ = [
    "BusinessLabConnector",
    "ConnectorRegistry",
    "IntegrationManager",
    "register_default_connectors",
    "registry",
]
