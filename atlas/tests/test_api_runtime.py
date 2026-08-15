from __future__ import annotations

import threading
from dataclasses import dataclass, field
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


@dataclass
class FakeService:
    gate: threading.Event | None = None
    started: bool = False
    closed: bool = False
    cancelled: bool = False
    thread_ids: list[int] = field(default_factory=list)

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
