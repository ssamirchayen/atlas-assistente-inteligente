from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from fastapi.testclient import TestClient

from atlas.api.app import create_app
from atlas.api.audit import (
    AuditStorageError,
    InMemoryAuditTrail,
    SqliteAuditTrail,
)
from atlas.api.auth import ApiKeyAuthenticator
from atlas.api.status import AtlasStatusService
from atlas.gui.service import GuiCommandResult
from atlas.version import API_VERSION

ADMIN_KEY = "atlas-admin-key-for-audit-tests-1234567890"
READ_KEY = "atlas-read-key-for-audit-tests-12345678901"


@dataclass
class FakeRuntime:
    result: GuiCommandResult = field(
        default_factory=lambda: GuiCommandResult(
            message="Resposta privada que não deve entrar na auditoria.",
            source="test",
            action_count=1,
        )
    )
    closed: bool = False

    def execute(
        self,
        command: str,
        *,
        workflow_id: str | None = None,
        requested_by: str | None = None,
    ) -> GuiCommandResult:
        del command, workflow_id, requested_by
        return self.result

    def close(self) -> None:
        self.closed = True


def make_client(
    audit: InMemoryAuditTrail,
    runtime: FakeRuntime | None = None,
    *,
    read_key: str = "",
) -> TestClient:
    return TestClient(
        create_app(
            AtlasStatusService(),
            ApiKeyAuthenticator.from_keys(
                admin_key=ADMIN_KEY,
                read_key=read_key,
            ),
            runtime or FakeRuntime(),
            audit,
        )
    )


def admin_headers() -> dict[str, str]:
    return {"X-API-Key": ADMIN_KEY}


def test_sqlite_audit_persists_without_raw_sensitive_values(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "api_audit.db"
    secret_command = "envie o relatório financeiro reservado"
    first = SqliteAuditTrail(database_path)
    first.record(
        "command.received",
        outcome="accepted",
        status_code=202,
        principal_id="local-admin",
        workflow_id="workflow-persistent",
        details={
            "command": secret_command,
            "category": "automation",
        },
    )
    first.close()

    second = SqliteAuditTrail(database_path)
    events = second.list_events(limit=10)
    second.close()

    assert len(events) == 1
    assert events[0].workflow_id == "workflow-persistent"
    assert events[0].details["category"] == "automation"
    redacted = events[0].details["command"]
    assert isinstance(redacted, dict)
    assert redacted["redacted"] is True
    assert redacted["length"] == len(secret_command)
    assert secret_command.encode() not in database_path.read_bytes()


def test_sqlite_audit_applies_maximum_event_retention(
    tmp_path: Path,
) -> None:
    trail = SqliteAuditTrail(
        tmp_path / "limited.db",
        max_events=2,
    )

    for index in range(3):
        trail.record(
            f"test.event_{index}",
            outcome="succeeded",
            status_code=200,
        )

    events = trail.list_events(limit=10)

    assert [event.event_type for event in events] == [
        "test.event_2",
        "test.event_1",
    ]


def test_authentication_attempts_are_audited_without_api_key() -> None:
    audit = InMemoryAuditTrail()
    client = make_client(audit)
    invalid_key = "invalid-api-key-that-must-never-be-persisted"

    response = client.get(
        f"/api/{API_VERSION}/status",
        headers={"X-API-Key": invalid_key},
    )
    serialized = json.dumps(
        [event.details for event in audit.list_events(limit=10)]
    )

    assert response.status_code == 401
    assert audit.list_events(limit=10)[0].event_type == (
        "authentication.rejected"
    )
    assert invalid_key not in serialized


def test_completed_command_is_audited_by_fingerprint_only() -> None:
    audit = InMemoryAuditTrail()
    client = make_client(audit)
    command = "Atlas, liste o relatório confidencial do cliente 42"

    response = client.post(
        f"/api/{API_VERSION}/commands",
        headers=admin_headers(),
        json={"command": command},
    )
    events = audit.list_events(
        limit=10,
        event_type="command.completed",
    )
    serialized = json.dumps([event.details for event in events])

    assert response.status_code == 200
    assert len(events) == 1
    assert events[0].workflow_id == response.json()["request_id"]
    assert events[0].outcome == "succeeded"
    assert events[0].details["command_length"] == len(command)
    assert len(str(events[0].details["command_sha256"])) == 64
    assert command not in serialized
    assert response.json()["message"] not in serialized


def test_audit_endpoint_requires_admin_scope_and_supports_filters() -> None:
    audit = InMemoryAuditTrail()
    audit.record(
        "command.completed",
        outcome="succeeded",
        status_code=200,
        workflow_id="workflow-filtered",
    )
    client = make_client(audit, read_key=READ_KEY)

    unauthorized = client.get(f"/api/{API_VERSION}/audit/events")
    monitor = client.get(
        f"/api/{API_VERSION}/audit/events",
        headers={"X-API-Key": READ_KEY},
    )
    admin = client.get(
        f"/api/{API_VERSION}/audit/events",
        headers=admin_headers(),
        params={
            "event_type": "command.completed",
            "workflow_id": "workflow-filtered",
            "limit": 10,
        },
    )

    assert unauthorized.status_code == 401
    assert monitor.status_code == 403
    assert monitor.json()["detail"] == "Permissão necessária: audit:read."
    assert admin.status_code == 200
    assert admin.json()["count"] == 1
    assert admin.json()["items"][0]["workflow_id"] == (
        "workflow-filtered"
    )


def test_api_adds_security_headers_and_rejects_untrusted_host() -> None:
    client = make_client(InMemoryAuditTrail())

    response = client.get(f"/api/{API_VERSION}/health")
    untrusted = client.get(
        f"/api/{API_VERSION}/health",
        headers={"Host": "example.invalid"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert untrusted.status_code == 400


class UnavailableAuditTrail(InMemoryAuditTrail):
    def list_events(
        self,
        *,
        limit: int,
        event_type: str | None = None,
        workflow_id: str | None = None,
    ):
        del limit, event_type, workflow_id
        raise AuditStorageError("storage offline")


def test_audit_endpoint_hides_storage_errors() -> None:
    response = make_client(UnavailableAuditTrail()).get(
        f"/api/{API_VERSION}/audit/events",
        headers=admin_headers(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "A auditoria local está temporariamente indisponível."
    )
    assert "storage offline" not in response.text


def test_openapi_documents_audit_security() -> None:
    schema = make_client(InMemoryAuditTrail()).get("/openapi.json").json()
    operation = schema["paths"][f"/api/{API_VERSION}/audit/events"]["get"]

    assert operation["security"] == [{"AtlasApiKey": []}]
