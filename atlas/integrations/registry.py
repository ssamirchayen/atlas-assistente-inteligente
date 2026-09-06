from __future__ import annotations

from .base import IntegrationConnector


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, IntegrationConnector] = {}

    def register(
        self,
        connector: IntegrationConnector,
        *,
        replace: bool = False,
    ) -> None:
        name = connector.name.strip().lower()
        if not name:
            raise ValueError("Connector sem nome.")

        if name in self._connectors and not replace:
            raise ValueError(
                f"Connector '{name}' já registrado."
            )

        self._connectors[name] = connector

    def unregister(self, name: str) -> None:
        self._connectors.pop(name.strip().lower(), None)

    def get(self, name: str) -> IntegrationConnector:
        normalized = name.strip().lower()
        try:
            return self._connectors[normalized]
        except KeyError as error:
            raise KeyError(
                f"Connector '{normalized}' não registrado."
            ) from error

    def has(self, name: str) -> bool:
        return name.strip().lower() in self._connectors

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._connectors))


registry = ConnectorRegistry()
