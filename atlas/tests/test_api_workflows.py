from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient

from atlas.api.app import create_app
from atlas.api.auth import ApiKeyAuthenticator
from atlas.api.runtime import (
    AtlasApiRuntime,
    CommandRuntime,
    RuntimeWorkflowNotCancellableError,
    RuntimeWorkflowNotFoundError,
    WorkflowRuntimeSnapshot,
    WorkflowRuntimeStatus,
)
from atlas.api.status import AtlasStatusService
from atlas.gui.service import GuiCommandResult
from atlas.version import API_VERSION

ADMIN_KEY = "atlas-admin-key-for-workflow-tests-123456789"
READ_KEY = "atlas-read-key-for-workflow-tests-1234567890"


def make_snapshot(
    workflow_id: str = "workflow-123",
    *,
    status: WorkflowRuntimeStatus = "running",
) -> WorkflowRuntimeSnapshot:
    now = datetime.now(timezone.utc)
    return WorkflowRuntimeSnapshot(
        workflow_id=workflow_id,
        status=status,
        requested_by="local-admin",
        created_at=now,
        started_at=now,
        finished_at=None,
        duration_ms=12.5,
        progress=0.5,
        completed_steps=1,
        total_steps=2,
        current_step="browser.search",
        message=None,
        source=None,
        success=None,
        cancelled=False,
        cancellation_requested=False,
        cancellation_reason=None,
        cancellation_requested_by=None,
    )


@dataclass
class FakeWorkflowRuntime:
    snapshots: dict[str, WorkflowRuntimeSnapshot] = field(default_factory=dict)
    cancellations: list[tuple[str, str, str]] = field(default_factory=list)
    closed: bool = False

    def execute(
        self,
        command: str,
        *,
        workflow_id: str | None = None,
        requested_by: str | None = None,
    ) -> GuiCommandResult:
        del workflow_id, requested_by
        return GuiCommandResult(message=command, source="test")

    def get_workflow(self, workflow_id: str) -> WorkflowRuntimeSnapshot:
        try:
            return self.snapshots[workflow_id]
        except KeyError as error:
            raise RuntimeWorkflowNotFoundError(workflow_id) from error

    def cancel_workflow(
        self,
        workflow_id: str,
        *,
        reason: str,
        requested_by: str,
    ) -> WorkflowRuntimeSnapshot:
        snapshot = self.get_workflow(workflow_id)

        if snapshot.status != "running":
            raise RuntimeWorkflowNotCancellableError(workflow_id)

        self.cancellations.append((workflow_id, reason, requested_by))
        updated = replace(
            snapshot,
            cancellation_requested=True,
            cancellation_reason=reason,
            cancellation_requested_by=requested_by,
        )
        self.snapshots[workflow_id] = updated
        return updated

    def close(self) -> None:
        self.closed = True


@dataclass
class SlowWorkflowService:
    gate: threading.Event = field(default_factory=threading.Event)
    started: bool = False
    cancelled: bool = False

    def start(self) -> None:
        self.started = True

    def execute(self, command: str) -> GuiCommandResult:
        self.gate.wait(timeout=2)
        return GuiCommandResult(
            message=command,
            source="workflow",
            success=not self.cancelled,
            action_count=2,
            cancelled=self.cancelled,
        )

    def cancel(
        self,
        *,
        reason: str,
        requested_by: str,
    ) -> bool:
        del reason, requested_by
        self.cancelled = True
        self.gate.set()
        return True

    def workflow_snapshot(self) -> SimpleNamespace:
        return SimpleNamespace(
            progress=0.5,
            completed_steps=1,
            total_steps=2,
            current_step="system.wait",
            cancelled=self.cancelled,
        )

    def close(self) -> None:
        self.gate.set()


def make_client(
    runtime: CommandRuntime,
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


def test_admin_can_query_workflow_status() -> None:
    snapshot = make_snapshot()
    runtime = FakeWorkflowRuntime({snapshot.workflow_id: snapshot})

    response = make_client(runtime).get(
        f"/api/{API_VERSION}/workflows/{snapshot.workflow_id}",
        headers=admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_id"] == snapshot.workflow_id
    assert payload["status"] == "running"
    assert payload["progress"] == 0.5
    assert payload["completed_steps"] == 1
    assert payload["total_steps"] == 2
    assert payload["current_step"] == "browser.search"


def test_workflow_query_requires_workflow_scope() -> None:
    snapshot = make_snapshot()
    runtime = FakeWorkflowRuntime({snapshot.workflow_id: snapshot})
    client = make_client(runtime, read_key=READ_KEY)

    missing = client.get(
        f"/api/{API_VERSION}/workflows/{snapshot.workflow_id}"
    )
    monitor = client.get(
        f"/api/{API_VERSION}/workflows/{snapshot.workflow_id}",
        headers={"X-API-Key": READ_KEY},
    )

    assert missing.status_code == 401
    assert monitor.status_code == 403
    assert monitor.json()["detail"] == (
        "Permissão necessária: workflows:read."
    )


def test_unknown_workflow_returns_not_found() -> None:
    response = make_client(FakeWorkflowRuntime()).get(
        f"/api/{API_VERSION}/workflows/inexistente",
        headers=admin_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workflow não encontrado."


def test_admin_can_request_workflow_cancellation() -> None:
    snapshot = make_snapshot()
    runtime = FakeWorkflowRuntime({snapshot.workflow_id: snapshot})

    response = make_client(runtime).post(
        f"/api/{API_VERSION}/workflows/{snapshot.workflow_id}/cancel",
        headers=admin_headers(),
        json={"reason": "  Interromper processamento  "},
    )

    assert response.status_code == 202
    payload = response.json()
    assert runtime.cancellations == [
        (
            snapshot.workflow_id,
            "Interromper processamento",
            "local-admin",
        )
    ]
    assert payload["cancellation_requested"] is True
    assert payload["cancellation_reason"] == "Interromper processamento"
    assert payload["cancellation_requested_by"] == "local-admin"


def test_finished_workflow_returns_conflict_on_cancel() -> None:
    snapshot = make_snapshot(status="completed")
    runtime = FakeWorkflowRuntime({snapshot.workflow_id: snapshot})

    response = make_client(runtime).post(
        f"/api/{API_VERSION}/workflows/{snapshot.workflow_id}/cancel",
        headers=admin_headers(),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "O workflow não está ativo ou não pode ser cancelado."
    )


def test_openapi_documents_workflow_security() -> None:
    schema = make_client(FakeWorkflowRuntime()).get("/openapi.json").json()
    base_path = f"/api/{API_VERSION}/workflows/{{workflow_id}}"

    assert schema["paths"][base_path]["get"]["security"] == [
        {"AtlasApiKey": []}
    ]
    assert schema["paths"][f"{base_path}/cancel"]["post"][
        "security"
    ] == [{"AtlasApiKey": []}]


def test_timeout_workflow_can_be_queried_and_cancelled_end_to_end() -> None:
    service = SlowWorkflowService()
    runtime = AtlasApiRuntime(
        service_factory=lambda: service,
        timeout_seconds=0.01,
    )
    client = make_client(runtime)

    with client:
        command_response = client.post(
            f"/api/{API_VERSION}/commands",
            headers=admin_headers(),
            json={"command": "aguarde 30 segundos"},
        )
        workflow_id = command_response.headers["X-Workflow-ID"]

        status_response = client.get(
            f"/api/{API_VERSION}/workflows/{workflow_id}",
            headers=admin_headers(),
        )
        cancel_response = client.post(
            f"/api/{API_VERSION}/workflows/{workflow_id}/cancel",
            headers=admin_headers(),
            json={"reason": "Interromper teste integrado"},
        )

        final_payload: dict[str, object] = {}
        for _ in range(200):
            final_payload = client.get(
                f"/api/{API_VERSION}/workflows/{workflow_id}",
                headers=admin_headers(),
            ).json()
            if final_payload["status"] == "cancelled":
                break
            threading.Event().wait(0.005)

    assert command_response.status_code == 504
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "running"
    assert status_response.json()["current_step"] == "system.wait"
    assert cancel_response.status_code == 202
    assert cancel_response.json()["cancellation_requested"] is True
    assert final_payload["status"] == "cancelled"
    assert final_payload["cancelled"] is True
