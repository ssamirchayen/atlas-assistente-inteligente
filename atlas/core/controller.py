from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING

from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.scheduler.job import ScheduledJob
from atlas.workflow.state import WorkflowState

if TYPE_CHECKING:
    from atlas.core.kernel import AtlasKernel


@dataclass(frozen=True, slots=True)
class WorkflowProgressSnapshot:
    """Visão consistente e somente leitura do workflow ativo."""

    progress: float
    completed_steps: int
    total_steps: int
    current_step: str | None
    cancelled: bool


class AtlasController:
    """
    Orquestra o agendamento, planejamento
    e execução dos comandos do Atlas.
    """

    def __init__(
        self,
        kernel: AtlasKernel,
    ) -> None:
        self.kernel = kernel
        self._workflow_lock = Lock()
        self._active_workflow: WorkflowState | None = None

    @property
    def active_workflow(self) -> WorkflowState | None:
        """Retorna o workflow em execução, quando existir."""

        with self._workflow_lock:
            return self._active_workflow

    def cancel_active_workflow(
        self,
        *,
        reason: str | None = None,
        requested_by: str | None = None,
    ) -> bool:
        """Solicita o cancelamento do workflow atualmente em execução."""

        with self._workflow_lock:
            state = self._active_workflow

        if state is None or state.finished:
            return False

        return state.cancel(
            reason=reason,
            requested_by=requested_by,
        )

    def workflow_snapshot(self) -> WorkflowProgressSnapshot | None:
        """Retorna o progresso atual sem expor o estado mutável."""

        with self._workflow_lock:
            state = self._active_workflow

            if state is None:
                return None

            current_action = state.current_action

            return WorkflowProgressSnapshot(
                progress=state.progress,
                completed_steps=len(state.completed_steps),
                total_steps=len(state.steps),
                current_step=(
                    current_action.type
                    if current_action is not None
                    else None
                ),
                cancelled=state.cancelled,
            )

    def execute(
        self,
        command: str,
    ) -> tuple[list[Action], list[ExecutionResult]]:
        """
        Processa um comando completo.

        Fluxo:

        comando
            ↓
        SchedulerParser
            ↓
        Planner
            ↓
        WorkflowBuilder
            ↓
        WorkflowEngine
            ↓
        Executor
        """

        # ==========================================
        # Verificação de agendamento
        # ==========================================

        scheduled = self.kernel.scheduler_parser.parse(
            command
        )

        if scheduled is not None:

            job = ScheduledJob(
                title=scheduled.command,
                command=scheduled.command,
                run_at=scheduled.run_at,
                repeat=scheduled.repeat,
            )

            self.kernel.scheduler.add_job(job)

            result = ExecutionResult.ok(
                action_type="scheduler",
                message=(
                    "Tarefa agendada para "
                    f"{scheduled.run_at.strftime('%d/%m/%Y %H:%M')}"
                ),
            )

            return [], [result]

        # ==========================================
        # Planejamento
        # ==========================================

        actions = self.kernel.planner.plan(
            command
        )

        if not actions:
            return [], []

        # ==========================================
        # Conversão para Workflow
        # ==========================================

        steps = self.kernel.workflow_builder.build(
            actions
        )

        state = WorkflowState(
            steps=steps
        )

        # ==========================================
        # Execução pelo Workflow Engine
        # ==========================================

        with self._workflow_lock:
            self._active_workflow = state

        try:
            workflow_result = self.kernel.workflow_engine.execute(
                state
            )
        finally:
            with self._workflow_lock:
                if self._active_workflow is state:
                    self._active_workflow = None

        results = list(workflow_result.results)

        if workflow_result.cancelled:
            results.append(
                ExecutionResult.fail(
                    action_type="workflow",
                    message=(
                        "Workflow cancelado."
                        + (
                            f" Motivo: {workflow_result.cancellation_reason}"
                            if workflow_result.cancellation_reason
                            else ""
                        )
                    ),
                    error_code="workflow_cancelled",
                    retryable=False,
                    data={
                        "requested_by": (
                            workflow_result.cancellation_requested_by
                        ),
                        "cancelled_step": workflow_result.cancelled_step,
                    },
                )
            )

        return actions, results
