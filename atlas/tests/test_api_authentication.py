from __future__ import annotations

from fastapi.testclient import TestClient

from atlas.api.app import create_app
from atlas.api.auth import (
    ADMIN_SCOPES,
    ApiCredential,
    ApiKeyAuthenticator,
    ApiPrincipal,
)
from atlas.api.status import AtlasStatusService
from atlas.version import API_VERSION

ADMIN_KEY = "atlas-admin-key-for-auth-tests-1234567890"
READ_KEY = "atlas-read-key-for-auth-tests-12345678901"
NO_STATUS_KEY = "atlas-no-status-key-for-tests-123456789"


def make_client(authenticator: ApiKeyAuthenticator) -> TestClient:
    return TestClient(
        create_app(
            AtlasStatusService(),
            authenticator,
        )
    )


def test_health_and_version_are_public() -> None:
    client = make_client(ApiKeyAuthenticator())

    assert client.get(f"/api/{API_VERSION}/health").status_code == 200
    assert client.get(f"/api/{API_VERSION}/version").status_code == 200


def test_protected_endpoint_rejects_missing_key() -> None:
    client = make_client(
        ApiKeyAuthenticator.from_keys(admin_key=ADMIN_KEY)
    )

    response = client.get(f"/api/{API_VERSION}/status")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "APIKey"
    assert response.json()["detail"] == "Chave da API ausente ou inválida."


def test_protected_endpoint_rejects_invalid_key() -> None:
    client = make_client(
        ApiKeyAuthenticator.from_keys(admin_key=ADMIN_KEY)
    )

    response = client.get(
        f"/api/{API_VERSION}/status",
        headers={"X-API-Key": "invalid-key"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Chave da API ausente ou inválida."


def test_unconfigured_authentication_fails_closed() -> None:
    response = make_client(ApiKeyAuthenticator()).get(
        f"/api/{API_VERSION}/status"
    )

    assert response.status_code == 503
    assert "ATLAS_API_KEY" in response.json()["detail"]


def test_read_key_can_view_status_and_identity() -> None:
    client = make_client(
        ApiKeyAuthenticator.from_keys(
            admin_key=ADMIN_KEY,
            read_key=READ_KEY,
        )
    )
    headers = {"X-API-Key": READ_KEY}

    status_response = client.get(
        f"/api/{API_VERSION}/status",
        headers=headers,
    )
    identity_response = client.get(
        f"/api/{API_VERSION}/auth/me",
        headers=headers,
    )

    assert status_response.status_code == 200
    assert identity_response.status_code == 200
    assert identity_response.json() == {
        "principal_id": "local-monitor",
        "role": "monitor",
        "scopes": ["status:read"],
    }


def test_valid_key_without_scope_is_forbidden() -> None:
    authenticator = ApiKeyAuthenticator(
        (
            ApiCredential(
                key=NO_STATUS_KEY,
                principal=ApiPrincipal(
                    principal_id="test-limited",
                    role="limited",
                    scopes=frozenset(),
                ),
            ),
        )
    )
    response = make_client(authenticator).get(
        f"/api/{API_VERSION}/status",
        headers={"X-API-Key": NO_STATUS_KEY},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Permissão necessária: status:read."
    )


def test_admin_identity_contains_future_permissions() -> None:
    client = make_client(
        ApiKeyAuthenticator.from_keys(admin_key=ADMIN_KEY)
    )

    response = client.get(
        f"/api/{API_VERSION}/auth/me",
        headers={"X-API-Key": ADMIN_KEY},
    )

    assert response.status_code == 200
    assert response.json()["principal_id"] == "local-admin"
    assert response.json()["role"] == "admin"
    assert set(response.json()["scopes"]) == set(ADMIN_SCOPES)


def test_openapi_documents_header_authentication() -> None:
    client = make_client(
        ApiKeyAuthenticator.from_keys(admin_key=ADMIN_KEY)
    )
    schema = client.get("/openapi.json").json()

    security_scheme = schema["components"]["securitySchemes"]["AtlasApiKey"]
    assert security_scheme["type"] == "apiKey"
    assert security_scheme["in"] == "header"
    assert security_scheme["name"] == "X-API-Key"
    assert schema["paths"][f"/api/{API_VERSION}/status"]["get"][
        "security"
    ] == [{"AtlasApiKey": []}]


def test_short_key_is_rejected_during_configuration() -> None:
    try:
        ApiKeyAuthenticator.from_keys(admin_key="short")
    except ValueError as error:
        assert "pelo menos 32 caracteres" in str(error)
    else:
        raise AssertionError("Uma chave curta deveria ser rejeitada.")
