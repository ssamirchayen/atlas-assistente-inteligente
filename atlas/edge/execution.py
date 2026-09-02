"""Supervised execution service for trusted Atlas Edge tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from atlas.edge.agent import ITProvisioningAgent
from atlas.edge.profile_service import EdgeProfileService
from atlas.edge.profiles import EmployeeProfileCatalog, profile_digest
from atlas.edge.task_queue import EdgeExecutionTask, EdgeTaskQueue
from atlas.provisioning.executor import ProvisioningExecutor
from atlas.provisioning.models import (
    DeviceInventory,
    PackageRequirement,
    ProvisioningEvidence,
)
from atlas.provisioning.planner import ProvisioningPlanner


class ExecutionInventoryCollector(Protocol):
    def capture(
        self,
        packages: tuple[PackageRequirement, ...] = (),
    ) -> DeviceInventory: ...


@dataclass(frozen=True, slots=True)
class EdgeExecutionResult:
    task: EdgeExecutionTask
    evidence: ProvisioningEvidence


class EdgeExecutionService:
    """Consumes approved plans, revalidates them and executes one chosen task."""

    def __init__(
        self,
        *,
        agent: ITProvisioningAgent,
        profile_service: EdgeProfileService,
        queue: EdgeTaskQueue,
        catalog: EmployeeProfileCatalog,
        collector: ExecutionInventoryCollector,
        planner: ProvisioningPlanner,
        executor: ProvisioningExecutor,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._agent = agent
        self._profile_service = profile_service
        self._queue = queue
        self._catalog = catalog
        self._collector = collector
        self._planner = planner
        self._executor = executor
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def dry_run(self) -> bool:
        return self._executor.dry_run

    def list_tasks(self) -> tuple[EdgeExecutionTask, ...]:
        return self._queue.list()

    def get_task(self, task_id: str) -> EdgeExecutionTask:
        task = self._queue.get(task_id)
        if task is None:
            raise ValueError("A tarefa Edge não foi encontrada.")
        return task

    def enqueue_authorization(self, authorization_id: str) -> EdgeExecutionTask:
        authorization = self._profile_service.consume_authorized_configuration(
            authorization_id
        )
        state = self._require_active_device()
        preview = authorization.preview
        if (
            preview.device_id != state.identity.device_id
            or preview.organization_id != state.enrollment.organization_id
        ):
            raise PermissionError("A autorização pertence a outro dispositivo.")
        profile = self._catalog.get(preview.plan.profile_id)
        if profile_digest(profile) != preview.profile_digest:
            raise PermissionError("O perfil autorizado não está mais vigente.")
        return self._queue.enqueue(authorization)

    def execute_task(self, task_id: str) -> EdgeExecutionResult:
        self._require_active_device()
        task = self._queue.claim(task_id)
        try:
            state = self._require_active_device()
            if (
                task.device_id != state.identity.device_id
                or task.organization_id != state.enrollment.organization_id
            ):
                raise PermissionError("A tarefa pertence a outro dispositivo.")
            profile = self._catalog.get(task.plan.profile_id)
            if profile_digest(profile) != task.profile_digest:
                raise PermissionError("O perfil da tarefa foi alterado.")
            inventory = self._collector.capture(profile.packages)
            if inventory.fingerprint() != task.plan.inventory_fingerprint:
                raise PermissionError("O inventário mudou antes da execução.")
            rebuilt = self._planner.build(profile, inventory)
            if [step.as_dict() for step in rebuilt.steps] != [
                step.as_dict() for step in task.plan.steps
            ]:
                raise PermissionError("As etapas da fila não conferem com o perfil.")
            evidence = self._executor.apply(task.plan, inventory)
            completed = self._queue.complete(task.task_id, evidence)
            return EdgeExecutionResult(task=completed, evidence=evidence)
        except Exception as exc:
            self._queue.fail(task.task_id, _error_code(exc))
            raise

    def cancel_task(self, task_id: str) -> EdgeExecutionTask:
        return self._queue.cancel(task_id)

    def _require_active_device(self):
        state = self._agent.state
        if state.enrollment is None:
            raise PermissionError("O dispositivo ainda não está cadastrado.")
        if state.paused:
            raise PermissionError("O Atlas Edge está pausado neste dispositivo.")
        return state

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("O relógio da execução deve possuir fuso horário.")
        return value.astimezone(timezone.utc)


def _error_code(error: Exception) -> str:
    if isinstance(error, PermissionError):
        return "permission_denied"
    if isinstance(error, ValueError):
        return "validation_failed"
    if isinstance(error, RuntimeError):
        return "execution_failed"
    return "internal_error"
