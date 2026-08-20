from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from atlas.api.app import create_app
from atlas.api.auth import ApiKeyAuthenticator
from atlas.api.status import AtlasStatusService
from atlas.gui.service import GuiCommandResult
from atlas.session.models import (
    OperationalEvent,
    OperationalSession,
    SessionStatus,
    TimelineEventType,
)
from atlas.session.resumption import (
    ResumableStep,
    ResumptionPlan,
    ResumptionRisk,
    ResumptionStatus,
)
from atlas.version import API_VERSION

ADMIN_KEY = "atlas-admin-key-for-session-tests-123456789"
READ_KEY = "atlas-read-key-for-session-tests-1234567890"


def make_session() -> OperationalSession:
    now = datetime.now(timezone.utc)
    return OperationalSession(
        session_id="session-21",
        user_id="Ssamir",
        title="Sessão Sprint 21",
        status=SessionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        ended_at=None,
        context={},
    )


def make_event() -> OperationalEvent:
    return OperationalEvent(
        event_id="event-21",
        session_id="session-21",
        sequence=7,
        event_type=TimelineEventType.STEP_COMPLETED,
        occurred_at=datetime.now(timezone.utc),
        message="Pesquisa concluída.",
        workflow_id="workflow-21",
        action_type="browser.search",
        details={"step_number": 1},
    )


def make_plan() -> ResumptionPlan:
    return ResumptionPlan(
        session_id="session-21",
        status=ResumptionStatus.CONFIRMATION_REQUIRED,
        reason="A etapa pendente altera estado externo.",
        source_workflow_id="workflow-21",
        source_sequence=4,
        total_steps=2,
        completed_step_indexes=(0,),
        remaining_steps=(
            ResumableStep(
                step_index=1,
                action_type="browser.search",
                parameters={"query": "Atlas"},
                risk=ResumptionRisk.CONFIRMATION_REQUIRED,
                reason="A ação exige confirmação.",
            ),
        ),
        confirmation_token="resume-token-21",
    )


@dataclass
class FakeOperationalRuntime:
    sessions: tuple[OperationalSession, ...] = field(
        default_factory=lambda: (make_session(),)
    )
    events: tuple[OperationalEvent, ...] = field(
        default_factory=lambda: (make_event(),)
    )
    plan: ResumptionPlan = field(default_factory=make_plan)
    timeline_queries: list[tuple[str | None, int, int | None]] = field(
        default_factory=list
    )
    resume_calls: list[tuple[str | None, str | None, str | None]] = field(
        default_factory=list
    )
    closed: bool = False

    def list_operational_sessions(
        self,
        *,
        status: SessionStatus | None = None,
        limit: int = 20,
    ) -> tuple[OperationalSession, ...]:
        items = self.sessions

        if status is not None:
            items = tuple(item for item in items if item.status is status)

        return items[:limit]

    def get_operational_timeline(
        self,
        *,
        session_id: str | None = None,
        limit: int = 100,
        after_sequence: int | None = None,
    ) -> tuple[OperationalEvent, ...]:
        self.timeline_queries.append(
            (session_id, limit, after_sequence)
        )
        return tuple(
            event
            for event in self.events
            if event.session_id == session_id
            and (
                after_sequence is None
                or event.sequence > after_sequence
            )
        )[:limit]

    def get_resumption_plan(self) -> ResumptionPlan:
        return self.plan

    def resume_interrupted_workflow(
        self,
        *,
        confirmation_token: str | None = None,
        workflow_id: str | None = None,
        requested_by: str | None = None,
    ) -> GuiCommandResult:
        self.resume_calls.append(
            (confirmation_token, workflow_id, requested_by)
        )
        return GuiCommandResult(
            message="Workflow retomado com sucesso.",
            source="resumption",
            success=True,
            action_count=1,
        )

    def close(self) -> None:
        self.closed = True


def make_client(runtime: FakeOperationalRuntime) -> TestClient:
    authenticator = ApiKeyAuthenticator.from_keys(
        admin_key=ADMIN_KEY,
        read_key=READ_KEY,
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


def test_admin_lists_operational_sessions() -> None:
    response = make_client(FakeOperationalRuntime()).get(
        f"/api/{API_VERSION}/sessions?session_status=active&limit=5",
        headers=admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["limit"] == 5
    assert payload["items"][0]["session_id"] == "session-21"
    assert payload["items"][0]["current"] is True


def test_monitor_key_cannot_read_operational_history() -> None:
    response = make_client(FakeOperationalRuntime()).get(
        f"/api/{API_VERSION}/sessions",
        headers={"X-API-Key": READ_KEY},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Permissão necessária: sessions:read."
    )


def test_admin_queries_incremental_session_timeline() -> None:
    runtime = FakeOperationalRuntime()
    response = make_client(runtime).get(
        (
            f"/api/{API_VERSION}/sessions/session-21/timeline"
            "?after_sequence=3&limit=10"
        ),
        headers=admin_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert runtime.timeline_queries == [("session-21", 10, 3)]
    assert payload["latest_sequence"] == 7
    assert payload["items"][0]["event_type"] == "step.completed"
    assert payload["items"][0]["details"] == {"step_number": 1}


def test_admin_inspects_and_confirms_resumption() -> None:
    runtime = FakeOperationalRuntime()
    client = make_client(runtime)

    plan_response = client.get(
        f"/api/{API_VERSION}/resumption",
        headers=admin_headers(),
    )
    resume_response = client.post(
        f"/api/{API_VERSION}/resumption",
        headers=admin_headers(),
        json={"confirmation_token": "  resume-token-21  "},
    )

    assert plan_response.status_code == 200
    plan_payload = plan_response.json()
    assert plan_payload["can_resume"] is True
    assert plan_payload["requires_confirmation"] is True
    assert plan_payload["remaining_steps"][0]["step_number"] == 2

    assert resume_response.status_code == 200
    resume_payload = resume_response.json()
    assert resume_payload["success"] is True
    assert resume_payload["action_count"] == 1
    token, workflow_id, requested_by = runtime.resume_calls[0]
    assert token == "resume-token-21"
    assert workflow_id == resume_payload["request_id"]
    assert requested_by == "local-admin"


def test_openapi_documents_operational_security() -> None:
    schema = make_client(FakeOperationalRuntime()).get(
        "/openapi.json"
    ).json()

    for path, method in (
        (f"/api/{API_VERSION}/sessions", "get"),
        (
            f"/api/{API_VERSION}/sessions/{{session_id}}/timeline",
            "get",
        ),
        (f"/api/{API_VERSION}/resumption", "get"),
        (f"/api/{API_VERSION}/resumption", "post"),
    ):
        security = schema["paths"][path][method]["security"]
        assert security == [{"AtlasApiKey": []}]
