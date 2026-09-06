from __future__ import annotations

import webbrowser
from typing import Any

from ..base import DriverKind, IntegrationDriver, IntegrationResult


class BusinessLabBrowserDriver(IntegrationDriver):
    kind = DriverKind.BROWSER
    priority = 20

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def supports(self, action: str) -> bool:
        return action in {
            "open",
            "open_login",
            "open_leads",
            "open_reports",
        }

    def is_available(self) -> bool:
        return True

    def execute(
        self,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        path = kwargs.get("path")

        paths = {
            "open_login": "/login",
            "open_leads": "/leads",
            "open_reports": "/relatorios",
        }

        if action == "open":
            if not isinstance(path, str) or not path.strip():
                return IntegrationResult(
                    ok=False,
                    action=action,
                    driver=self.kind,
                    error="A ação open exige o argumento path.",
                )
            normalized = "/" + path.lstrip("/")
        else:
            normalized = paths.get(action, "")

        if not normalized:
            return IntegrationResult(
                ok=False,
                action=action,
                driver=self.kind,
                error="Ação de navegador inválida.",
            )

        url = f"{self.base_url}{normalized}"
        opened = webbrowser.open(
            url,
            new=2,
            autoraise=True,
        )

        return IntegrationResult(
            ok=bool(opened),
            action=action,
            driver=self.kind,
            data={"url": url},
            error=None if opened else "Navegador não abriu a URL.",
        )
