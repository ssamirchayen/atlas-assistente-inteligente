"""Catálogo central dos conectores disponíveis no Atlas."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock

from atlas.connectors.models import (
    ConnectorCapability,
    ConnectorManifest,
)


class ConnectorRegistry:
    """Registra manifests sem permitir substituição silenciosa."""

    def __init__(
        self,
        connectors: Iterable[ConnectorManifest] | None = None,
    ) -> None:
        self._connectors: dict[str, ConnectorManifest] = {}
        self._lock = RLock()

        for connector in connectors or ():
            self.register(connector)

    def register(self, connector: ConnectorManifest) -> None:
        if not isinstance(connector, ConnectorManifest):
            raise TypeError("O registro aceita apenas ConnectorManifest.")

        with self._lock:
            if connector.connector_id in self._connectors:
                raise ValueError(
                    "Já existe um conector registrado como "
                    f"'{connector.connector_id}'."
                )

            self._connectors[connector.connector_id] = connector

    def unregister(self, connector_id: str) -> bool:
        normalized_id = connector_id.strip().lower()

        with self._lock:
            return self._connectors.pop(normalized_id, None) is not None

    def get(self, connector_id: str) -> ConnectorManifest | None:
        normalized_id = connector_id.strip().lower()

        with self._lock:
            return self._connectors.get(normalized_id)

    def resolve(
        self,
        connector_id: str,
        capability_name: str,
    ) -> tuple[ConnectorManifest, ConnectorCapability] | None:
        connector = self.get(connector_id)

        if connector is None:
            return None

        capability = connector.get_capability(capability_name)

        if capability is None:
            return None

        return connector, capability

    def catalog(self) -> tuple[ConnectorManifest, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._connectors.values(),
                    key=lambda connector: connector.connector_id,
                )
            )
