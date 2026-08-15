from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from atlas.api.app import create_app
from atlas.api.auth import ApiKeyAuthenticator
from atlas.api.models import ResourceUsage
from atlas.api.status import AtlasStatusService
from atlas.version import API_VERSION, ATLAS_VERSION

ADMIN_KEY = "atlas-admin-key-for-tests-1234567890"


def make_client(
    authenticator: ApiKeyAuthenticator | None = None,
) -> TestClient:
    monotonic_values = iter((100.0, 112.5))
    service = AtlasStatusService(
        resource_reader=lambda: ResourceUsage(
            cpu_percent=12.0,
            memory_percent=34.0,
        ),
        clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
        monotonic_clock=lambda: next(monotonic_values),
    )
    api_authenticator = authenticator or ApiKeyAuthenticator.from_keys(
        admin_key=ADMIN_KEY,
    )
    return TestClient(create_app(service, api_authenticator))


def admin_headers() -> dict[str, str]:
    return {"X-API-Key": ADMIN_KEY}


def test_health_endpoint() -> None:
    response = make_client().get(f"/api/{API_VERSION}/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "atlas-api",
        "timestamp": "2026-08-14T12:00:00Z",
    }


def test_version_endpoint() -> None:
    response = make_client().get(f"/api/{API_VERSION}/version")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Atlas",
        "version": ATLAS_VERSION,
        "api_version": API_VERSION,
    }


def test_status_endpoint_reports_local_capabilities() -> None:
    response = make_client().get(
        f"/api/{API_VERSION}/status",
        headers=admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["mode"] == "local"
    assert payload["local_only"] is True
    assert payload["authentication_required"] is True
    assert payload["uptime_seconds"] == 12.5
    assert payload["resources"] == {
        "cpu_percent": 12.0,
        "memory_percent": 34.0,
    }
    assert payload["capabilities"]["workflow"] is True
    assert payload["capabilities"]["specialized_agents"] == [
        "browser",
        "coding",
        "desktop",
        "sales",
        "helpdesk",
        "hr",
    ]


def test_openapi_lists_observability_endpoints() -> None:
    response = make_client().get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert f"/api/{API_VERSION}/health" in paths
    assert f"/api/{API_VERSION}/version" in paths
    assert f"/api/{API_VERSION}/status" in paths
    assert f"/api/{API_VERSION}/auth/me" in paths
