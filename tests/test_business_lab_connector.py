from __future__ import annotations

from atlas.integrations.base import DriverKind
from atlas.integrations.business_lab import BusinessLabConnector


def test_business_lab_driver_order():
    connector = BusinessLabConnector(
        "http://127.0.0.1:5055"
    )

    kinds = [
        driver.kind
        for driver in sorted(
            connector.drivers,
            key=lambda item: item.priority,
        )
    ]

    assert kinds == [
        DriverKind.API,
        DriverKind.BROWSER,
        DriverKind.VISION,
    ]


def test_business_lab_has_expected_name():
    connector = BusinessLabConnector()

    assert connector.name == "business_lab"


def test_browser_supports_operational_navigation():
    connector = BusinessLabConnector()
    browser = next(
        driver
        for driver in connector.drivers
        if driver.kind is DriverKind.BROWSER
    )

    assert browser.supports("open_login")
    assert browser.supports("open_leads")
    assert browser.supports("open_reports")

def test_api_driver_supports_business_operations():
    connector = BusinessLabConnector()
    api = next(
        driver
        for driver in connector.drivers
        if driver.kind is DriverKind.API
    )

    assert api.supports("get_lead")
    assert api.supports("list_interactions")
    assert api.supports("create_followup")
    assert api.supports("get_reports")

