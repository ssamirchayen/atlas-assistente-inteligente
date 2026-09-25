from __future__ import annotations

from typing import Any

from ..base import (
    DriverKind,
    IntegrationConnector,
    IntegrationDriver,
    IntegrationResult,
)
from .client import NexyraClient, NexyraConfig, NexyraError


class NexyraApiDriver(IntegrationDriver):
    kind = DriverKind.API
    priority = 10

    def __init__(self, client: NexyraClient | None = None) -> None:
        self.client = client

    def supports(self, action: str) -> bool:
        return action in {
            "diagnose",
            "summary",
            "metrics",
            "pending",
            "sources",
            "queue",
            "sla",
            "recommendations",
            "dashboard",
            "team",
            "operations",
        }

    def is_available(self) -> bool:
        # A configuração é verificada ao executar, com erro útil ao usuário.
        return True

    def execute(self, action: str, **kwargs: Any) -> IntegrationResult:
        if not self.supports(action) or kwargs:
            return IntegrationResult(
                False, action, self.kind, error="Consulta Nexyra não suportada."
            )
        try:
            client = self.client or NexyraClient(NexyraConfig.from_env())
            if action in {
                "queue",
                "sla",
                "recommendations",
                "dashboard",
                "team",
                "operations",
            }:
                data = client.operations()
            else:
                data = client.snapshot()
        except NexyraError as exc:
            return IntegrationResult(
                False, action, self.kind, error=str(exc), metadata={"code": exc.code}
            )
        return IntegrationResult(True, action, self.kind, data=data)


class NexyraConnector(IntegrationConnector):
    def __init__(self, client: NexyraClient | None = None) -> None:
        self._drivers = (NexyraApiDriver(client),)

    @property
    def name(self) -> str:
        return "nexyra_crm"

    @property
    def drivers(self) -> tuple[IntegrationDriver, ...]:
        return self._drivers
