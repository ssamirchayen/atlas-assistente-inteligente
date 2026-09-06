from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DriverKind(str, Enum):
    API = "api"
    BROWSER = "browser"
    VISION = "vision"


@dataclass(frozen=True, slots=True)
class IntegrationResult:
    ok: bool
    action: str
    driver: DriverKind | None = None
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class IntegrationDriver(ABC):
    kind: DriverKind
    priority: int = 100

    @abstractmethod
    def supports(self, action: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def execute(
        self,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        raise NotImplementedError


class IntegrationConnector(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def drivers(self) -> tuple[IntegrationDriver, ...]:
        raise NotImplementedError

    def execute(
        self,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        candidates = sorted(
            (
                driver
                for driver in self.drivers
                if driver.supports(action)
            ),
            key=lambda driver: driver.priority,
        )

        if not candidates:
            return IntegrationResult(
                ok=False,
                action=action,
                error=(
                    f"Nenhum driver do connector '{self.name}' "
                    f"suporta a ação '{action}'."
                ),
            )

        errors: list[str] = []

        for driver in candidates:
            if not driver.is_available():
                errors.append(
                    f"{driver.kind.value}: indisponível"
                )
                continue

            result = driver.execute(action, **kwargs)
            if result.ok:
                return result

            errors.append(
                f"{driver.kind.value}: "
                f"{result.error or 'falha sem detalhe'}"
            )

        return IntegrationResult(
            ok=False,
            action=action,
            error="; ".join(errors) or "Nenhum driver disponível.",
        )
