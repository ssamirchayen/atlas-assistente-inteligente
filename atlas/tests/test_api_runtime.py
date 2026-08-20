from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace

from atlas.api.runtime import (
    AtlasApiRuntime,
    RuntimeBusyError,
    RuntimeClosedError,
    RuntimeTimeoutError,
    RuntimeWorkflowNotCancellableError,
    RuntimeWorkflowNotFoundError,
)
from atlas.gui.service import GuiCommandResult
from atlas.session.models import (
    OperationalEvent,
    OperationalSession,
    SessionStatus,
    TimelineEventType,
)
from atlas.session.resumption import ResumptionPlan


@dataclass
class FakeService:
    gate: threading.Event | None = None
    started: bool = False
    closed: bool = False
    cancelled: bool = False
    thread_ids: list[int] = field(default_factory=list)
    resume_tokens: list[str | None] = field(default_factory=list)

    def start(self) -> None:
        self.started = True
        self.thread_ids.append(threading.get_ident())

    def execute(self, command: str) -> GuiCommandResult:
        self.thread_ids.append(threading.get_ident())

        if self.gate is not None:
            self.gate.wait(timeout=2)

        return GuiCommandResult(
            message=command.upper(),
            source="test",
            success=not self.cancelled,
            action_count=1,
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

        if self.gate is not None:
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

    def list_operational_sessions(
        self,
        *,
        status: SessionStatus | None = None,
        limit: int = 20,
    ) -> tuple[OperationalSession, ...]:
        now = datetime.now(timezone.utc)
        session = OperationalSession(
            session_id="runtime-session",
            user_id="Ssamir",
            title="Sessão runtime",
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            ended_at=None,
            context={},
        )

        if status not in {None, session.status}:
            return ()

        return (session,)[:limit]

    def get_operational_timeline(
        self,
        *,
        session_id: str | None = None,
        limit: int = 100,
        after_sequence: int | None = None,
    ) -> tuple[OperationalEvent, ...]:
        event = OperationalEvent(
            event_id="runtime-event",
            session_id=session_id or "runtime-session",
            sequence=2,
            event_type=TimelineEventType.COMMAND_COMPLETED,
            occurred_at=datetime.now(timezone.utc),
            message="Comando concluído.",
            workflow_id="runtime-workflow",
            action_type=None,
            details={},
        )

        if after_sequence is not None and event.sequence <= after_sequence:
            return ()

        return (event,)[:limit]

    def get_resumption_plan(self) -> ResumptionPlan:
        return ResumptionPlan.not_available("runtime-session")

    def resume_interrupted_workflow(
        self,
        *,
        confirmation_token: str | None = None,
    ) -> GuiCommandResult:
        self.resume_tokens.append(confirmation_token)
        return GuiCommandResult(
            message="Retomada concluída.",
            source="resumption",
            action_count=1,
        )

    def close(self) -> None:
        self.closed = True
        self.thread_ids.append(threading.get_ident())


def test_runtime_is_lazy_and_reuses_worker_thread() -> None:
    service = FakeService()
    factory_calls = 0

    def factory() -> FakeService:
        nonlocal factory_calls
        factory_calls += 1
        return service

    runtime = AtlasApiRuntime(
        service_factory=factory,
        timeout_seconds=2,
    )

    assert factory_calls == 0
    assert runtime.execute("primeiro").message == "PRIMEIRO"
    assert runtime.execute("segundo").message == "SEGUNDO"
    runtime.close()

    assert factory_calls == 1
    assert service.started is True
    assert service.closed is True
    assert len(set(service.thread_ids)) == 1


def test_runtime_rejects_parallel_command() -> None:
    gate = threading.Event()
    service = FakeService(gate=gate)
    runtime = AtlasApiRuntime(
        service_factory=lambda: service,
        timeout_seconds=2,
    )
    finished = threading.Event()

    def execute_first() -> None:
        runtime.execute("primeiro")
        finished.set()

    thread = threading.Thread(target=execute_first)
    thread.start()
    while not runtime.busy:
        finished.wait(timeout=0.01)

    try:
        runtime.execute("segundo")
    except RuntimeBusyError:
        pass
    else:
        raise AssertionError("O segundo comando deveria ser rejeitado.")

    gate.set()
    thread.join(timeout=2)
    runtime.close()
    assert finished.is_set()


def test_timeout_keeps_runtime_busy_until_command_finishes() -> None:
    gate = threading.Event()
    runtime = AtlasApiRuntime(
        service_factory=lambda: FakeService(gate=gate),
        timeout_seconds=0.01,
    )

    try:
        runtime.execute("demorado")
    except RuntimeTimeoutError:
        pass
    else:
        raise AssertionError("O comando deveria exceder o timeout.")

    assert runtime.busy is True
    gate.set()

    for _ in range(200):
        if not runtime.busy:
            break
        threading.Event().wait(0.005)

    assert runtime.busy is False
    runtime.close()


def test_runtime_rejects_execution_after_close() -> None:
    runtime = AtlasApiRuntime(
        service_factory=FakeService,
        timeout_seconds=2,
    )
    runtime.close()

    try:
        runtime.execute("comando")
    except RuntimeClosedError:
        pass
    else:
        raise AssertionError("O runtime encerrado deveria rejeitar comandos.")


def test_completed_workflow_remains_queryable() -> None:
    runtime = AtlasApiRuntime(
        service_factory=FakeService,
        timeout_seconds=2,
    )

    result = runtime.execute(
        "concluir",
        workflow_id="workflow-completed",
        requested_by="local-admin",
    )
    snapshot = runtime.get_workflow("workflow-completed")
    runtime.close()

    assert result.success is True
    assert snapshot.status == "completed"
    assert snapshot.requested_by == "local-admin"
    assert snapshot.progress == 1.0
    assert snapshot.completed_steps == 1
    assert snapshot.total_steps == 1
    assert snapshot.message == "CONCLUIR"


def test_running_workflow_can_be_observed_and_cancelled() -> None:
    gate = threading.Event()
    service = FakeService(gate=gate)
    runtime = AtlasApiRuntime(
        service_factory=lambda: service,
        timeout_seconds=2,
    )
    finished = threading.Event()

    def execute() -> None:
        runtime.execute(
            "aguarde",
            workflow_id="workflow-running",
            requested_by="local-admin",
        )
        finished.set()

    thread = threading.Thread(target=execute)
    thread.start()

    for _ in range(200):
        if service.started:
            break
        threading.Event().wait(0.005)

    running = runtime.get_workflow("workflow-running")
    cancellation = runtime.cancel_workflow(
        "workflow-running",
        reason="Solicitado no teste",
        requested_by="pytest",
    )
    thread.join(timeout=2)
    cancelled = runtime.get_workflow("workflow-running")
    runtime.close()

    assert running.status == "running"
    assert running.progress == 0.5
    assert running.current_step == "system.wait"
    assert cancellation.cancellation_requested is True
    assert cancellation.cancellation_reason == "Solicitado no teste"
    assert cancellation.cancellation_requested_by == "pytest"
    assert finished.is_set()
    assert cancelled.status == "cancelled"
    assert cancelled.cancelled is True


def test_unknown_workflow_is_rejected() -> None:
    runtime = AtlasApiRuntime(service_factory=FakeService)

    try:
        runtime.get_workflow("inexistente")
    except RuntimeWorkflowNotFoundError:
        pass
    else:
        raise AssertionError("O workflow inexistente deveria ser rejeitado.")
    finally:
        runtime.close()


def test_completed_workflow_cannot_be_cancelled() -> None:
    runtime = AtlasApiRuntime(service_factory=FakeService)
    runtime.execute("concluir", workflow_id="workflow-finished")

    try:
        runtime.cancel_workflow(
            "workflow-finished",
            reason="Tarde demais",
            requested_by="pytest",
        )
    except RuntimeWorkflowNotCancellableError:
        pass
    else:
        raise AssertionError("O workflow concluído não deveria ser cancelado.")
    finally:
        runtime.close()


def test_runtime_exposes_operational_queries_lazily() -> None:
    service = FakeService()
    runtime = AtlasApiRuntime(
        service_factory=lambda: service,
        timeout_seconds=2,
    )

    sessions = runtime.list_operational_sessions(limit=5)
    events = runtime.get_operational_timeline(
        session_id="runtime-session",
        after_sequence=1,
    )
    plan = runtime.get_resumption_plan()
    runtime.close()

    assert service.started is True
    assert sessions[0].session_id == "runtime-session"
    assert events[0].sequence == 2
    assert plan.session_id == "runtime-session"


def test_runtime_tracks_resumed_workflow() -> None:
    service = FakeService()
    runtime = AtlasApiRuntime(
        service_factory=lambda: service,
        timeout_seconds=2,
    )

    result = runtime.resume_interrupted_workflow(
        confirmation_token="runtime-token",
        workflow_id="resumed-workflow",
        requested_by="local-admin",
    )
    snapshot = runtime.get_workflow("resumed-workflow")
    runtime.close()

    assert result.success is True
    assert service.resume_tokens == ["runtime-token"]
    assert snapshot.status == "completed"
    assert snapshot.source == "resumption"
    assert snapshot.requested_by == "local-admin"
