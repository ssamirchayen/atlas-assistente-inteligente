from __future__ import annotations

from typing import Any

from .base import IntegrationResult
from .registry import ConnectorRegistry, registry


class IntegrationManager:
    def __init__(
        self,
        connector_registry: ConnectorRegistry | None = None,
    ) -> None:
        self.registry = connector_registry or registry

    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        try:
            connector = self.registry.get(connector_name)
        except KeyError as error:
            return IntegrationResult(
                ok=False,
                action=action,
                error=str(error),
            )

        return connector.execute(action, **kwargs)

    def available_connectors(self) -> tuple[str, ...]:
        return self.registry.names()
