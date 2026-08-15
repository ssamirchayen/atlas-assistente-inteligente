from __future__ import annotations

from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from atlas.api.app import create_app
from atlas.api.auth import ApiKeyAuthenticator
from atlas.api.runtime import (
    RuntimeBusyError,
    RuntimeClosedError,
    RuntimeTimeoutError,
)
from atlas.api.status import AtlasStatusService
from atlas.gui.service import GuiCommandResult
from atlas.version import API_VERSION

ADMIN_KEY = "atlas-admin-key-for-command-tests-123456789"
READ_KEY = "atlas-read-key-for-command-tests-1234567890"


@dataclass
class FakeRuntime:
    result: GuiCommandResult = field(
        default_factory=lambda: GuiCommandResult(
            message="Comando executado.",
            source="workflow",
            action_count=1,
        )
    )
    error: Exception | None = None
    commands: list[str] = field(default_factory=list)
    workflow_ids: list[str | None] = field(default_factory=list)
    requested_by: list[str | None] = field(default_factory=list)
    closed: bool = False

    def execute(
        self,
        command: str,
        *,
        workflow_id: str | None = None,
        requested_by: str | None = None,
    ) -> GuiCommandResult:
        self.commands.append(command)
        self.workflow_ids.append(workflow_id)
        self.requested_by.append(requested_by)

        if self.error is not None:
            raise self.error

        return self.result

    def close(self) -> None:
        self.closed = True


def make_client(
    runtime: FakeRuntime,
    *,
    read_key: str = "",
) -> TestClient:
    authenticator = ApiKeyAuthenticator.from_keys(
        admin_key=ADMIN_KEY,
        read_key=read_key,
    )
    return TestClient(
        create_app(
            AtlasStatusService(),
            authenticator,
            runtime,
        )
    )


def admin_headers() -> dict[str, str]:
    return {"X-API-Key": ADMIN_KEY}


def test_admin_executes_command() -> None:
    runtime = FakeRuntime()
    response = make_client(runtime).post(
        f"/api/{API_VERSION}/commands",
        headers=admin_headers(),
        json={"command": "  Atlas, abra o navegador  "},
    )

    assert response.status_code == 200
    payload = response.json()
    assert runtime.commands == ["Atlas, abra o navegador"]
    assert payload["message"] == "Comando executado."
    assert payload["source"] == "workflow"
    assert payload["success"] is True
    assert payload["action_count"] == 1
    assert payload["cancelled"] is False
    assert payload["should_close"] is False
    assert payload["request_id"]
    assert runtime.workflow_ids == [payload["request_id"]]
    assert runtime.requested_by == ["local-admin"]
    assert payload["duration_ms"] >= 0


def test_command_requires_authentication() -> None:
    runtime = FakeRuntime()
    response = make_client(runtime).post(
        f"/api/{API_VERSION}/commands",
        json={"command": "abra o navegador"},
    )

    assert response.status_code == 401
    assert runtime.commands == []


def test_monitor_cannot_execute_command() -> None:
    runtime = FakeRuntime()
    response = make_client(runtime, read_key=READ_KEY).post(
        f"/api/{API_VERSION}/commands",
        headers={"X-API-Key": READ_KEY},
        json={"command": "abra o navegador"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Permissão necessária: commands:execute."
    )
    assert runtime.commands == []


def test_blank_command_is_rejected_before_runtime() -> None:
    runtime = FakeRuntime()
    response = make_client(runtime).post(
        f"/api/{API_VERSION}/commands",
        headers=admin_headers(),
        json={"command": "   "},
    )

    assert response.status_code == 422
    assert runtime.commands == []


def test_busy_runtime_returns_conflict() -> None:
    runtime = FakeRuntime(error=RuntimeBusyError())
    response = make_client(runtime).post(
        f"/api/{API_VERSION}/commands",
        headers=admin_headers(),
        json={"command": "comando simultâneo"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "O Atlas já está executando outro comando."
    )


def test_runtime_timeout_is_explicit() -> None:
    runtime = FakeRuntime(error=RuntimeTimeoutError())
    response = make_client(runtime).post(
        f"/api/{API_VERSION}/commands",
        headers=admin_headers(),
        json={"command": "comando demorado"},
    )

    assert response.status_code == 504
    assert "execução continua" in response.json()["detail"]
    assert response.headers["X-Workflow-ID"] == runtime.workflow_ids[0]


def test_closed_runtime_returns_service_unavailable() -> None:
    runtime = FakeRuntime(error=RuntimeClosedError())
    response = make_client(runtime).post(
        f"/api/{API_VERSION}/commands",
        headers=admin_headers(),
        json={"command": "abra o navegador"},
    )

    assert response.status_code == 503


def test_internal_error_does_not_expose_exception() -> None:
    runtime = FakeRuntime(error=RuntimeError("segredo interno"))
    response = make_client(runtime).post(
        f"/api/{API_VERSION}/commands",
        headers=admin_headers(),
        json={"command": "abra o navegador"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Falha interna ao executar o comando."
    )
    assert "segredo interno" not in response.text


def test_runtime_closes_with_application_lifespan() -> None:
    runtime = FakeRuntime()

    with make_client(runtime) as client:
        assert client.get(f"/api/{API_VERSION}/health").status_code == 200
        assert runtime.closed is False

    assert runtime.closed is True


def test_openapi_documents_command_endpoint_security() -> None:
    runtime = FakeRuntime()
    schema = make_client(runtime).get("/openapi.json").json()
    operation = schema["paths"][f"/api/{API_VERSION}/commands"]["post"]

    assert operation["security"] == [{"AtlasApiKey": []}]
    assert operation["requestBody"]["required"] is True
