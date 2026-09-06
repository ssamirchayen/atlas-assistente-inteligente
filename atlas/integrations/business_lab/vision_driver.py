from __future__ import annotations

from typing import Any

from ..base import DriverKind, IntegrationDriver, IntegrationResult


class BusinessLabVisionDriver(IntegrationDriver):
    kind = DriverKind.VISION
    priority = 30

    def supports(self, action: str) -> bool:
        return action.startswith("vision.")

    def is_available(self) -> bool:
        # A ligação com Atlas Vision entra em etapa posterior.
        return False

    def execute(
        self,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        del kwargs
        return IntegrationResult(
            ok=False,
            action=action,
            driver=self.kind,
            error="Driver Vision ainda não conectado.",
        )
