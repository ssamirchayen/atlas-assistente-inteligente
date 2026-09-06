from __future__ import annotations

from typing import Any

import pytest

from atlas.integrations.base import (
    DriverKind,
    IntegrationConnector,
    IntegrationDriver,
    IntegrationResult,
)
from atlas.integrations.manager import IntegrationManager
from atlas.integrations.registry import ConnectorRegistry


class FakeDriver(IntegrationDriver):
    def __init__(
        self,
        kind: DriverKind,
        *,
        priority: int,
        available: bool,
        ok: bool,
    ) -> None:
        self.kind = kind
        self.priority = priority
        self.available = available
        self.ok = ok
        self.calls = 0

    def supports(self, action: str) -> bool:
        return action == "read"

    def is_available(self) -> bool:
        return self.available

    def execute(
        self,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult:
        del kwargs
        self.calls += 1
        return IntegrationResult(
            ok=self.ok,
            action=action,
            driver=self.kind,
            data={"driver": self.kind.value}
            if self.ok
            else None,
            error=None if self.ok else "falhou",
        )


class FakeConnector(IntegrationConnector):
    def __init__(
        self,
        *drivers: IntegrationDriver,
    ) -> None:
        self._drivers = tuple(drivers)

    @property
    def name(self) -> str:
        return "fake"

    @property
    def drivers(self) -> tuple[IntegrationDriver, ...]:
        return self._drivers


def test_api_is_preferred_when_available():
    api = FakeDriver(
        DriverKind.API,
        priority=10,
        available=True,
        ok=True,
    )
    browser = FakeDriver(
        DriverKind.BROWSER,
        priority=20,
        available=True,
        ok=True,
    )
    connector = FakeConnector(browser, api)

    result = connector.execute("read")

    assert result.ok is True
    assert result.driver is DriverKind.API
    assert api.calls == 1
    assert browser.calls == 0


def test_browser_is_fallback_when_api_is_unavailable():
    api = FakeDriver(
        DriverKind.API,
        priority=10,
        available=False,
        ok=False,
    )
    browser = FakeDriver(
        DriverKind.BROWSER,
        priority=20,
        available=True,
        ok=True,
    )
    connector = FakeConnector(api, browser)

    result = connector.execute("read")

    assert result.ok is True
    assert result.driver is DriverKind.BROWSER
    assert api.calls == 0
    assert browser.calls == 1


def test_vision_can_be_final_fallback():
    api = FakeDriver(
        DriverKind.API,
        priority=10,
        available=False,
        ok=False,
    )
    browser = FakeDriver(
        DriverKind.BROWSER,
        priority=20,
        available=False,
        ok=False,
    )
    vision = FakeDriver(
        DriverKind.VISION,
        priority=30,
        available=True,
        ok=True,
    )
    connector = FakeConnector(api, browser, vision)

    result = connector.execute("read")

    assert result.ok is True
    assert result.driver is DriverKind.VISION


def test_registry_rejects_duplicate_connector():
    registry = ConnectorRegistry()
    connector = FakeConnector()

    registry.register(connector)

    with pytest.raises(ValueError, match="já registrado"):
        registry.register(connector)


def test_manager_returns_error_for_unknown_connector():
    manager = IntegrationManager(ConnectorRegistry())

    result = manager.execute(
        "unknown",
        "read",
    )

    assert result.ok is False
    assert "não registrado" in result.error
