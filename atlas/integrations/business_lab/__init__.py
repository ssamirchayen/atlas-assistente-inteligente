from __future__ import annotations

from dataclasses import dataclass

from .connector import BusinessLabConnector, DEFAULT_BASE_URL


@dataclass(frozen=True, slots=True)
class BusinessLabHealth:
    reachable: bool
    status: str
    service: str | None = None
    version: str | None = None
    schema_version: int | None = None
    error: str | None = None


class BusinessLabBridge:
    """Compatibilidade temporária com a Etapa 1 antiga."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.connector = BusinessLabConnector(base_url)
        api_driver = self.connector.drivers[0]
        api_driver.timeout_seconds = timeout_seconds

    @property
    def base_url(self) -> str:
        return self.connector.drivers[0].base_url

    @property
    def health_url(self) -> str:
        return f"{self.base_url}/health"

    @property
    def login_url(self) -> str:
        return f"{self.base_url}/login"

    def health(self) -> BusinessLabHealth:
        result = self.connector.execute("health")
        payload = result.data or {}
        return BusinessLabHealth(
            reachable=result.ok,
            status=str(payload.get("status", "unreachable")),
            service=payload.get("service"),
            version=payload.get("version"),
            schema_version=payload.get("schema_version"),
            error=result.error,
        )

    def open_login(self) -> bool:
        return self.connector.execute("open_login").ok

    def open_path(self, path: str) -> bool:
        return self.connector.execute(
            "open",
            path=path,
        ).ok


def create_business_lab_connector() -> BusinessLabConnector:
    return BusinessLabConnector()


def create_business_lab_bridge() -> BusinessLabBridge:
    return BusinessLabBridge()


__all__ = [
    "BusinessLabBridge",
    "BusinessLabConnector",
    "BusinessLabHealth",
    "DEFAULT_BASE_URL",
    "create_business_lab_bridge",
    "create_business_lab_connector",
]
