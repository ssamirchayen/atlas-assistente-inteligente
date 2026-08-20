from __future__ import annotations

from dataclasses import dataclass
import logging
from threading import Lock
from typing import TYPE_CHECKING
from uuid import uuid4

from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.scheduler.job import ScheduledJob
from atlas.session.models import TimelineEventType
from atlas.session.resumption import (
    ResumptionPlan,
    ResumptionStatus,
    WorkflowResumptionPlanner,
)
from atlas.session.storage import SessionStorageError
from atlas.workflow.state import WorkflowState

if TYPE_CHECKING:
    from atlas.core.kernel import AtlasKernel

_LOGGER = logging.getLogger(__name__)


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
        self._resumption_lock = Lock()
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

    def get_resumption_plan(self) -> ResumptionPlan:
        """Retorna a decisão segura para o último workflow interrompido."""

        session = getattr(self.kernel, "session", None)
        get_plan = getattr(session, "get_resumption_plan", None)

        if not callable(get_plan):
            return ResumptionPlan.not_available(
                "unknown",
                "A sessão operacional não oferece suporte à retomada.",
            )

        return get_plan()

    def resume_interrupted_workflow(
        self,
        *,
        confirmation_token: str | None = None,
    ) -> tuple[list[Action], list[ExecutionResult]]:
        """Retoma somente etapas pendentes após validar risco e confirmação."""

        with self._resumption_lock:
            if self.active_workflow is not None:
                return [], [
                    self._resumption_failure(
                        self.get_resumption_plan(),
                        error_code="workflow_resume_busy",
                        message=(
                            "Já existe um workflow em execução. Aguarde ou "
                            "cancele-o antes de solicitar uma retomada."
                        ),
                    )
                ]

            plan = self.get_resumption_plan()

            if plan.status is ResumptionStatus.NOT_AVAILABLE:
                return [], [
                    self._resumption_failure(
                        plan,
                        error_code="workflow_resume_not_available",
                        message=plan.reason,
                    )
                ]

            if plan.status is ResumptionStatus.BLOCKED:
                self._record_event(
                    TimelineEventType.WORKFLOW_RESUME_BLOCKED,
                    plan.reason,
                    workflow_id=plan.source_workflow_id,
                    action_type="workflow.resume",
                    details=plan.as_dict(),
                )
                return [], [
                    self._resumption_failure(
                        plan,
                        error_code="workflow_resume_blocked",
                        message=plan.reason,
                    )
                ]

            if (
                plan.requires_confirmation
                and confirmation_token != plan.confirmation_token
            ):
                self._record_event(
                    TimelineEventType.WORKFLOW_RESUME_CONFIRMATION_REQUIRED,
                    plan.reason,
                    workflow_id=plan.source_workflow_id,
                    action_type="workflow.resume",
                    details={
                        "source_sequence": plan.source_sequence,
                        "remaining_steps": len(plan.remaining_steps),
                    },
                )
                return [], [
                    self._resumption_failure(
                        plan,
                        error_code="workflow_resume_confirmation_required",
                        message=(
                            "Confirme a retomada usando o token do plano "
                            "antes de repetir as ações pendentes."
                        ),
                    )
                ]

            actions = plan.to_actions()
            operation_id = str(uuid4())
            resumed = self._record_event(
                TimelineEventType.WORKFLOW_RESUMED,
                "Workflow interrompido encaminhado para retomada segura.",
                workflow_id=plan.source_workflow_id,
                action_type="workflow.resume",
                details={
                    "resume_token": plan.confirmation_token,
                    "resumed_workflow_id": operation_id,
                    "completed_step_indexes": list(
                        plan.completed_step_indexes
                    ),
                    "remaining_step_indexes": [
                        step.step_index for step in plan.remaining_steps
                    ],
                    "confirmation_required": plan.requires_confirmation,
                    "confirmed": plan.requires_confirmation,
                },
            )

            if not resumed:
                return [], [
                    self._resumption_failure(
                        plan,
                        error_code="workflow_resume_audit_unavailable",
                        message=(
                            "A retomada não foi executada porque não foi "
                            "possível registrar sua trilha de auditoria."
                        ),
                    )
                ]

            return self._execute_actions(
                actions,
                operation_id,
                resumed_from=plan,
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

        operation_id = str(uuid4())
        self._record_event(
            TimelineEventType.COMMAND_RECEIVED,
            "Comando recebido pelo núcleo.",
            workflow_id=operation_id,
            details={"command": command},
        )

        try:
            return self._execute_recorded(command, operation_id)
        except Exception as error:
            self._record_event(
                TimelineEventType.COMMAND_FAILED,
                "O comando foi interrompido por uma falha interna.",
                workflow_id=operation_id,
                details={
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            raise

    def _execute_recorded(
        self,
        command: str,
        operation_id: str,
    ) -> tuple[list[Action], list[ExecutionResult]]:
        scheduled = self.kernel.scheduler_parser.parse(command)

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
            self._record_event(
                TimelineEventType.TASK_SCHEDULED,
                result.message,
                workflow_id=operation_id,
                action_type="scheduler",
                details={
                    "command": scheduled.command,
                    "run_at": scheduled.run_at.isoformat(),
                    "repeat": scheduled.repeat,
                },
            )
            self._record_event(
                TimelineEventType.COMMAND_COMPLETED,
                "O comando foi concluído pelo agendador.",
                workflow_id=operation_id,
                details={"result_count": 1},
            )
            return [], [result]

        actions = self.kernel.planner.plan(command)

        if not actions:
            self._record_event(
                TimelineEventType.COMMAND_UNHANDLED,
                "Nenhuma ação operacional foi criada para o comando.",
                workflow_id=operation_id,
            )
            return [], []

        return self._execute_actions(actions, operation_id)

    def _execute_actions(
        self,
        actions: list[Action],
        operation_id: str,
        *,
        resumed_from: ResumptionPlan | None = None,
    ) -> tuple[list[Action], list[ExecutionResult]]:
        """Executa ações já validadas e registra seu ciclo operacional."""

        steps = self.kernel.workflow_builder.build(actions)
        state = WorkflowState(steps=steps)
        serialized_actions = WorkflowResumptionPlanner.serialize_actions(
            actions
        )
        start_details: dict[str, object] = {
            "plan_version": 1,
            "step_count": len(steps),
            "action_types": [action.type for action in actions],
            "actions": serialized_actions,
        }

        if resumed_from is not None:
            start_details["resumed_from_workflow_id"] = (
                resumed_from.source_workflow_id
            )
            start_details["resume_token"] = resumed_from.confirmation_token
            start_details["source_step_indexes"] = [
                step.step_index for step in resumed_from.remaining_steps
            ]

        self._record_event(
            TimelineEventType.WORKFLOW_STARTED,
            f"Workflow iniciado com {len(steps)} etapa(s).",
            workflow_id=operation_id,
            details=start_details,
        )

        with self._workflow_lock:
            self._active_workflow = state

        try:
            workflow_result = self.kernel.workflow_engine.execute(state)
        finally:
            with self._workflow_lock:
                if self._active_workflow is state:
                    self._active_workflow = None

        results = list(workflow_result.results)
        self._record_step_results(
            results,
            workflow_id=operation_id,
            actions=actions,
        )

        if workflow_result.cancelled:
            cancellation = ExecutionResult.fail(
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
            results.append(cancellation)
            self._record_event(
                TimelineEventType.WORKFLOW_CANCELLED,
                cancellation.message,
                workflow_id=operation_id,
                action_type="workflow",
                details=cancellation.data,
            )
        elif workflow_result.success:
            self._record_event(
                TimelineEventType.WORKFLOW_COMPLETED,
                "Workflow concluído com sucesso.",
                workflow_id=operation_id,
                details={
                    "completed_steps": workflow_result.completed_steps,
                    "total_steps": workflow_result.total_steps,
                },
            )
        else:
            self._record_event(
                TimelineEventType.WORKFLOW_FAILED,
                workflow_result.error or "O workflow falhou.",
                workflow_id=operation_id,
                details={
                    "completed_steps": workflow_result.completed_steps,
                    "total_steps": workflow_result.total_steps,
                },
            )

        return actions, results

    def _record_step_results(
        self,
        results: list[ExecutionResult],
        *,
        workflow_id: str,
        actions: list[Action],
    ) -> None:
        for step_index, result in enumerate(results):
            planned_action_type = (
                actions[step_index].type
                if step_index < len(actions)
                else result.action_type
            )
            self._record_event(
                (
                    TimelineEventType.STEP_COMPLETED
                    if result.success
                    else TimelineEventType.STEP_FAILED
                ),
                result.message,
                workflow_id=workflow_id,
                action_type=result.action_type,
                details={
                    "success": result.success,
                    "step_index": step_index,
                    "step_number": step_index + 1,
                    "planned_action_type": planned_action_type,
                    "error_code": result.error_code,
                    "retryable": result.retryable,
                    "duration_seconds": result.duration,
                    "attempts": result.attempts,
                    "index": result.index,
                    "total": result.total,
                    "data": result.data,
                },
            )

    @staticmethod
    def _resumption_failure(
        plan: ResumptionPlan,
        *,
        error_code: str,
        message: str,
    ) -> ExecutionResult:
        return ExecutionResult.fail(
            action_type="workflow.resume",
            message=message,
            error_code=error_code,
            retryable=False,
            data={"resumption_plan": plan.as_dict()},
        )

    def _record_event(
        self,
        event_type: TimelineEventType,
        message: str,
        *,
        workflow_id: str | None = None,
        action_type: str | None = None,
        details: dict[str, object] | None = None,
    ) -> bool:
        session = getattr(self.kernel, "session", None)
        record_event = getattr(session, "record_event", None)

        if not callable(record_event):
            return False

        try:
            record_event(
                event_type,
                message,
                workflow_id=workflow_id,
                action_type=action_type,
                details=details,
            )
            return True
        except (SessionStorageError, TypeError, ValueError):
            _LOGGER.exception(
                "Falha não bloqueante ao registrar evento operacional"
            )
            return False
