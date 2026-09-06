from __future__ import annotations

import io
import json
from urllib.error import HTTPError

from atlas.integrations.base import DriverKind
from atlas.integrations.business_lab.api_driver import (
    BusinessLabApiDriver,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_driver_supports_operational_actions():
    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055"
    )

    assert driver.supports("get_lead")
    assert driver.supports("create_followup")
    assert driver.supports("update_enrollment")
    assert not driver.supports("scenario_answer")


def test_authentication_caches_token(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse(
            {
                "ok": True,
                "data": {
                    "token": "token-123",
                    "token_type": "Bearer",
                },
            }
        )

    monkeypatch.setattr(
        "atlas.integrations.business_lab.api_driver.urlopen",
        fake_urlopen,
    )

    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055",
        email="consultor@nexyra.lab",
        password="Consultor123!",
    )

    result = driver.execute("authenticate")

    assert result.ok is True
    assert driver._token == "token-123"
    assert calls[0].full_url.endswith(
        "/api/v1/auth/login"
    )


def test_get_lead_authenticates_and_reads(monkeypatch):
    responses = iter(
        [
            FakeResponse(
                {
                    "ok": True,
                    "data": {
                        "token": "token-abc",
                    },
                }
            ),
            FakeResponse(
                {
                    "ok": True,
                    "data": {
                        "synthetic_code": "SIM-00001",
                        "name": "Lead Teste",
                    },
                }
            ),
        ]
    )

    def fake_urlopen(request, timeout):
        return next(responses)

    monkeypatch.setattr(
        "atlas.integrations.business_lab.api_driver.urlopen",
        fake_urlopen,
    )

    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055",
        email="consultor@nexyra.lab",
        password="Consultor123!",
    )

    result = driver.execute(
        "get_lead",
        code="SIM-00001",
    )

    assert result.ok is True
    assert result.driver is DriverKind.API
    assert result.data["synthetic_code"] == "SIM-00001"


def test_list_leads_builds_query(monkeypatch):
    requested_urls = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse(
            {
                "ok": True,
                "data": [],
                "meta": {"count": 0},
            }
        )

    monkeypatch.setattr(
        "atlas.integrations.business_lab.api_driver.urlopen",
        fake_urlopen,
    )

    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055",
    )
    driver._token = "existing"

    result = driver.execute(
        "list_leads",
        query="SIM-00001",
        priority="alta",
        limit=10,
    )

    assert result.ok is True
    assert "q=SIM-00001" in requested_urls[0]
    assert "priority=alta" in requested_urls[0]
    assert "limit=10" in requested_urls[0]


def test_create_interaction_sends_json(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["method"] = request.method
        captured["body"] = json.loads(
            request.data.decode("utf-8")
        )
        return FakeResponse(
            {
                "ok": True,
                "data": {"id": 99},
            }
        )

    monkeypatch.setattr(
        "atlas.integrations.business_lab.api_driver.urlopen",
        fake_urlopen,
    )

    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055",
    )
    driver._token = "existing"

    result = driver.execute(
        "create_interaction",
        code="SIM-00005",
        channel="WhatsApp",
        kind="mensagem",
        direction="saida",
        outcome="interessado",
        content="Teste",
    )

    assert result.ok is True
    assert captured["method"] == "POST"
    assert captured["body"]["content"] == "Teste"


def test_http_api_error_is_preserved(monkeypatch):
    payload = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "lead_not_found",
                "message": "Lead não encontrado.",
            },
        }
    ).encode("utf-8")

    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            404,
            "Not Found",
            {},
            io.BytesIO(payload),
        )

    monkeypatch.setattr(
        "atlas.integrations.business_lab.api_driver.urlopen",
        fake_urlopen,
    )

    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055",
    )
    driver._token = "existing"

    result = driver.execute(
        "get_lead",
        code="SIM-99999",
    )

    assert result.ok is False
    assert result.error == "Lead não encontrado."
    assert (
        result.metadata["api_error_code"]
        == "lead_not_found"
    )


def test_missing_required_argument_returns_failure():
    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055",
    )

    result = driver.execute("get_lead")

    assert result.ok is False
    assert "code" in result.error


def test_api_driver_does_not_support_benchmark_answers():
    driver = BusinessLabApiDriver(
        "http://127.0.0.1:5055"
    )

    forbidden = {
        "get_scenario",
        "scenario_reference",
        "benchmark_answer",
        "official_answer",
    }

    assert all(
        not driver.supports(action)
        for action in forbidden
    )
