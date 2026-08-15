"""Runtime serial, preguiçoso e observável usado pela API."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import uuid4

from atlas.core.config import API_COMMAND_TIMEOUT

if TYPE_CHECKING:
    from atlas.gui.service import GuiCommandResult

WorkflowRuntimeStatus = Literal[
    "running",
    "completed",
    "failed",
    "cancelled",
]


class WorkflowProgress(Protocol):
    """Progresso mínimo exposto pelo núcleo durante a execução."""

    progress: float
    completed_steps: int
    total_steps: int
    current_step: str | None
    cancelled: bool


class CommandService(Protocol):
    """Contrato mínimo do serviço operacional usado pela API."""

    def start(self) -> None: ...

    def execute(self, command: str) -> GuiCommandResult: ...

    def cancel(
        self,
        *,
        reason: str,
        requested_by: str,
    ) -> bool: ...

    def workflow_snapshot(self) -> WorkflowProgress | None: ...

    def close(self) -> None: ...


class CommandRuntime(Protocol):
    """Contrato injetável consumido pela aplicação FastAPI."""

    def execute(
        self,
        command: str,
        *,
        workflow_id: str | None = None,
        requested_by: str | None = None,
    ) -> GuiCommandResult: ...

    def get_workflow(self, workflow_id: str) -> WorkflowRuntimeSnapshot: ...

    def cancel_workflow(
        self,
        workflow_id: str,
        *,
        reason: str,
        requested_by: str,
    ) -> WorkflowRuntimeSnapshot: ...

    def close(self) -> None: ...


class RuntimeBusyError(RuntimeError):
    """Indica que já existe um comando em execução."""


class RuntimeTimeoutError(RuntimeError):
    """Indica que a espera HTTP terminou antes do comando."""


class RuntimeClosedError(RuntimeError):
    """Indica tentativa de uso após o encerramento do runtime."""


class RuntimeWorkflowNotFoundError(LookupError):
    """Indica que o identificador não pertence ao histórico do runtime."""


class RuntimeWorkflowNotCancellableError(RuntimeError):
    """Indica que a execução não possui workflow ativo cancelável."""


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeSnapshot:
    """Visão imutável e segura de uma execução submetida à API."""

    workflow_id: str
    status: WorkflowRuntimeStatus
    requested_by: str | None
    created_at: datetime
    started_at: datetime
    finished_at: datetime | None
    duration_ms: float
    progress: float
    completed_steps: int
    total_steps: int
    current_step: str | None
    message: str | None
    source: str | None
    success: bool | None
    cancelled: bool
    cancellation_requested: bool
    cancellation_reason: str | None
    cancellation_requested_by: str | None


@dataclass(slots=True)
class _WorkflowRecord:
    workflow_id: str
    requested_by: str | None
    created_at: datetime
    started_at: datetime
    status: WorkflowRuntimeStatus = "running"
    finished_at: datetime | None = None
    progress: float = 0.0
    completed_steps: int = 0
    total_steps: int = 0
    current_step: str | None = None
    message: str | None = None
    source: str | None = None
    success: bool | None = None
    cancelled: bool = False
    cancellation_requested: bool = False
    cancellation_reason: str | None = None
    cancellation_requested_by: str | None = None


ServiceFactory = Callable[[], CommandService]


def create_default_service() -> CommandService:
    """Importa e cria o núcleo somente na primeira execução real."""

    from atlas.gui.service import AtlasGuiService

    return AtlasGuiService()


class AtlasApiRuntime:
    """Mantém o núcleo em uma thread e registra as execuções recentes."""

    def __init__(
        self,
        *,
        service_factory: ServiceFactory = create_default_service,
        timeout_seconds: float = API_COMMAND_TIMEOUT,
        max_workflow_records: int = 100,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("O timeout da API deve ser maior que zero.")

        if max_workflow_records <= 0:
            raise ValueError("O limite de workflows deve ser maior que zero.")

        self._service_factory = service_factory
        self._timeout_seconds = timeout_seconds
        self._max_workflow_records = max_workflow_records
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="atlas-api-command",
        )
        self._state_lock = Lock()
        self._service: CommandService | None = None
        self._workflows: dict[str, _WorkflowRecord] = {}
        self._busy = False
        self._closed = False

    @property
    def busy(self) -> bool:
        with self._state_lock:
            return self._busy

    def execute(
        self,
        command: str,
        *,
        workflow_id: str | None = None,
        requested_by: str | None = None,
    ) -> GuiCommandResult:
        execution_id = workflow_id or str(uuid4())
        now = datetime.now(timezone.utc)

        with self._state_lock:
            if self._closed:
                raise RuntimeClosedError

            if self._busy:
                raise RuntimeBusyError

            if execution_id in self._workflows:
                raise ValueError("O identificador do workflow já existe.")

            self._evict_old_records_locked()
            self._workflows[execution_id] = _WorkflowRecord(
                workflow_id=execution_id,
                requested_by=requested_by,
                created_at=now,
                started_at=now,
            )
            self._busy = True

        try:
            future = self._executor.submit(self._execute_on_worker, command)
        except Exception:
            with self._state_lock:
                self._workflows.pop(execution_id, None)
                self._busy = False
            raise

        future.add_done_callback(
            lambda completed: self._command_finished(
                execution_id,
                completed,
            )
        )

        try:
            return future.result(timeout=self._timeout_seconds)
        except TimeoutError as error:
            raise RuntimeTimeoutError from error

    def get_workflow(self, workflow_id: str) -> WorkflowRuntimeSnapshot:
        self._refresh_progress(workflow_id)

        with self._state_lock:
            record = self._workflows.get(workflow_id)

            if record is None:
                raise RuntimeWorkflowNotFoundError(workflow_id)

            return self._snapshot_locked(record)

    def cancel_workflow(
        self,
        workflow_id: str,
        *,
        reason: str,
        requested_by: str,
    ) -> WorkflowRuntimeSnapshot:
        clean_reason = reason.strip() or "Cancelado pela API."

        with self._state_lock:
            record = self._workflows.get(workflow_id)

            if record is None:
                raise RuntimeWorkflowNotFoundError(workflow_id)

            if record.status == "cancelled":
                return self._snapshot_locked(record)

            if record.status != "running":
                raise RuntimeWorkflowNotCancellableError(workflow_id)

            if record.cancellation_requested:
                return self._snapshot_locked(record)

            service = self._service

        if service is None:
            raise RuntimeWorkflowNotCancellableError(workflow_id)

        changed = service.cancel(
            reason=clean_reason,
            requested_by=requested_by,
        )

        if not changed:
            raise RuntimeWorkflowNotCancellableError(workflow_id)

        with self._state_lock:
            record = self._workflows[workflow_id]
            record.cancellation_requested = True
            record.cancellation_reason = clean_reason
            record.cancellation_requested_by = requested_by

        self._refresh_progress(workflow_id)

        with self._state_lock:
            return self._snapshot_locked(self._workflows[workflow_id])

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return

            self._closed = True

        cleanup = self._executor.submit(self._close_on_worker)
        cleanup.result()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _execute_on_worker(self, command: str) -> GuiCommandResult:
        if self._service is None:
            service = self._service_factory()

            try:
                service.start()
            except Exception:
                service.close()
                raise

            self._service = service

        return self._service.execute(command)

    def _close_on_worker(self) -> None:
        if self._service is None:
            return

        self._service.close()
        self._service = None

    def _command_finished(
        self,
        workflow_id: str,
        future: Future[GuiCommandResult],
    ) -> None:
        finished_at = datetime.now(timezone.utc)

        try:
            result = future.result()
        except Exception:
            with self._state_lock:
                record = self._workflows[workflow_id]
                record.status = "failed"
                record.finished_at = finished_at
                record.message = "Falha interna ao executar o comando."
                record.success = False
                record.current_step = None
                self._busy = False
            return

        with self._state_lock:
            record = self._workflows[workflow_id]
            record.finished_at = finished_at
            record.message = result.message
            record.source = result.source
            record.success = result.success
            record.cancelled = result.cancelled
            record.current_step = None
            record.total_steps = max(record.total_steps, result.action_count)

            if result.cancelled:
                record.status = "cancelled"
            elif result.success:
                record.status = "completed"
                record.progress = 1.0
                record.completed_steps = record.total_steps
            else:
                record.status = "failed"

            self._busy = False

    def _refresh_progress(self, workflow_id: str) -> None:
        with self._state_lock:
            record = self._workflows.get(workflow_id)

            if record is None or record.status != "running":
                return

            service = self._service

        if service is None:
            return

        progress = service.workflow_snapshot()

        if progress is None:
            return

        with self._state_lock:
            record = self._workflows.get(workflow_id)

            if record is None or record.status != "running":
                return

            record.progress = min(max(progress.progress, 0.0), 1.0)
            record.completed_steps = max(progress.completed_steps, 0)
            record.total_steps = max(progress.total_steps, 0)
            record.current_step = progress.current_step
            record.cancelled = progress.cancelled

    def _evict_old_records_locked(self) -> None:
        while len(self._workflows) >= self._max_workflow_records:
            removable_id = next(
                (
                    workflow_id
                    for workflow_id, record in self._workflows.items()
                    if record.status != "running"
                ),
                None,
            )

            if removable_id is None:
                break

            self._workflows.pop(removable_id)

    @staticmethod
    def _duration_ms(record: _WorkflowRecord) -> float:
        end = record.finished_at or datetime.now(timezone.utc)
        return max(
            round((end - record.started_at).total_seconds() * 1000, 3),
            0.0,
        )

    def _snapshot_locked(
        self,
        record: _WorkflowRecord,
    ) -> WorkflowRuntimeSnapshot:
        return WorkflowRuntimeSnapshot(
            workflow_id=record.workflow_id,
            status=record.status,
            requested_by=record.requested_by,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            duration_ms=self._duration_ms(record),
            progress=record.progress,
            completed_steps=record.completed_steps,
            total_steps=record.total_steps,
            current_step=record.current_step,
            message=record.message,
            source=record.source,
            success=record.success,
            cancelled=record.cancelled,
            cancellation_requested=record.cancellation_requested,
            cancellation_reason=record.cancellation_reason,
            cancellation_requested_by=record.cancellation_requested_by,
        )
