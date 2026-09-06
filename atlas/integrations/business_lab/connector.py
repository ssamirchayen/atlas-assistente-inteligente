from __future__ import annotations

import os

from ..base import IntegrationConnector, IntegrationDriver
from .api_driver import BusinessLabApiDriver
from .browser_driver import BusinessLabBrowserDriver
from .vision_driver import BusinessLabVisionDriver

DEFAULT_BASE_URL = "http://127.0.0.1:5055"


class BusinessLabConnector(IntegrationConnector):
    def __init__(
        self,
        base_url: str | None = None,
        *,
        email: str | None = None,
        password: str | None = None,
    ) -> None:
        configured = (
            base_url
            or os.getenv("ATLAS_BUSINESS_LAB_URL")
            or DEFAULT_BASE_URL
        )
        normalized = configured.rstrip("/")

        api_email = (
            email
            or os.getenv("ATLAS_BUSINESS_LAB_EMAIL")
        )
        api_password = (
            password
            or os.getenv("ATLAS_BUSINESS_LAB_PASSWORD")
        )

        self._drivers: tuple[IntegrationDriver, ...] = (
            BusinessLabApiDriver(
                normalized,
                email=api_email,
                password=api_password,
            ),
            BusinessLabBrowserDriver(normalized),
            BusinessLabVisionDriver(),
        )

    @property
    def name(self) -> str:
        return "business_lab"

    @property
    def drivers(self) -> tuple[IntegrationDriver, ...]:
        return self._drivers
