from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from atlas.planner.results import ExecutionResult
from atlas.planner.task_manager import TaskManager
from atlas.workflow.cancellation import WorkflowCancelledError
from atlas.workflow.result import WorkflowResult
from atlas.workflow.state import WorkflowState

if TYPE_CHECKING:
    from atlas.planner.executor import Executor

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
INITIAL_RETRY_DELAY = 1.0
RETRY_BACKOFF_FACTOR = 2.0


class WorkflowEngine:
    """
    Orquestra a execução de um workflow.

    Responsabilidades:
        - controlar a ordem das etapas;
        - avaliar condições;
        - acompanhar progresso;
        - armazenar contexto da execução;
        - gerenciar tarefas;
        - consolidar o resultado final;
        - registrar telemetria da execução;
        - repetir ações com falhas recuperáveis.
    """

    def __init__(
        self,
        executor: Executor,
        task_manager: TaskManager,
    ) -> None:
        self.executor = executor
        self.task_manager = task_manager

    def execute(
        self,
        state: WorkflowState,
    ) -> WorkflowResult:
        workflow_id = str(uuid4())[:8]
        workflow_started_at = time.perf_counter()

        results: list[ExecutionResult] = []
        total_steps = len(state.steps)

        logger.info(
            "[Workflow %s] Iniciado com %d etapa(s).",
            workflow_id,
            total_steps,
        )

        active_task_id: str | None = None
        active_action_type: str | None = None

        try:
            state.throw_if_cancelled()

            while state.has_next:
                state.throw_if_cancelled()
                step_number = state.current_index + 1
                step = state.next_step()

                if step is None:
                    break

                state.throw_if_cancelled()
                action = step.action
                active_action_type = action.type

                logger.info(
                "[Workflow %s] Etapa %d/%d: %s.",
                workflow_id,
                step_number,
                total_steps,
                action.type,
                )

                if not step.should_execute(
                    state.context.data
                ):
                    logger.info(
                    "[Workflow %s] Etapa %d/%d ignorada: %s.",
                    workflow_id,
                    step_number,
                    total_steps,
                    action.type,
                    )

                    state.context.add_history(
                    "step_skipped",
                    action=action.type,
                    workflow_id=workflow_id,
                    )

                    state.mark_skipped()
                    active_action_type = None
                    continue

                state.throw_if_cancelled()
                task = self.task_manager.create_task(
                    description=action.type,
                    action=action,
                )
                active_task_id = task.id

                self.task_manager.start_task(task.id)

                step_started_at = time.perf_counter()

                result = self._execute_with_retry(
                    action=action,
                    workflow_id=workflow_id,
                    step_number=step_number,
                    total_steps=total_steps,
                    state=state,
                )
                state.throw_if_cancelled()

                step_duration = time.perf_counter() - step_started_at

                results.append(result)

                state.context.set_result(result)

                state.context.add_history(
                (
                    "step_completed"
                    if result.success
                    else "step_failed"
                ),
                action=action.type,
                success=result.success,
                duration=step_duration,
                workflow_id=workflow_id,
                )

                if result.success:
                    state.mark_completed()
                    self.task_manager.complete_task(task.id, result)
                    active_task_id = None
                    active_action_type = None
                    state.throw_if_cancelled()

                    logger.info(
                    (
                        "[Workflow %s] Etapa %d/%d concluída: "
                        "%s (%.2fs)."
                    ),
                    workflow_id,
                    step_number,
                    total_steps,
                    action.type,
                    step_duration,
                    )

                    continue

                self.task_manager.fail_task(task.id, result)
                active_task_id = None

                state.mark_failed(result.message)

                workflow_duration = time.perf_counter() - workflow_started_at

                logger.error(
                (
                    "[Workflow %s] Etapa %d/%d falhou: "
                    "%s (%.2fs). Erro: %s"
                ),
                workflow_id,
                step_number,
                total_steps,
                action.type,
                step_duration,
                result.message,
                )

                self._log_summary(
                workflow_id=workflow_id,
                state=state,
                duration=workflow_duration,
                success=False,
                )

                return WorkflowResult.failed_result(
                    completed_steps=len(state.completed_steps),
                    total_steps=total_steps,
                    results=results,
                    error=result.message,
                )
        except WorkflowCancelledError as error:
            return self._handle_cancellation(
                state=state,
                results=results,
                workflow_id=workflow_id,
                total_steps=total_steps,
                workflow_started_at=workflow_started_at,
                active_task_id=active_task_id,
                active_action_type=active_action_type,
                error=error,
            )

        workflow_duration = (
            time.perf_counter()
            - workflow_started_at
        )

        self._log_summary(
            workflow_id=workflow_id,
            state=state,
            duration=workflow_duration,
            success=True,
        )

        return WorkflowResult.success_result(
            results
        )

    def _execute_with_retry(
        self,
        *,
        action: Any,
        workflow_id: str,
        step_number: int,
        total_steps: int,
        state: WorkflowState | None = None,
    ) -> ExecutionResult:
        last_result: ExecutionResult | None = None
        retry_delay = INITIAL_RETRY_DELAY

        for attempt in range(
            1,
            MAX_ATTEMPTS + 1,
        ):
            if state is not None:
                state.throw_if_cancelled()
            logger.info(
                (
                    "[Workflow %s] Etapa %d/%d - "
                    "tentativa %d/%d: %s."
                ),
                workflow_id,
                step_number,
                total_steps,
                attempt,
                MAX_ATTEMPTS,
                action.type,
            )

            result = self._execute_action(
                action
            )

            if state is not None:
                state.throw_if_cancelled()

            if result.success:
                if attempt > 1:
                    logger.info(
                        (
                            "[Workflow %s] Ação %s concluída "
                            "após %d tentativa(s)."
                        ),
                        workflow_id,
                        action.type,
                        attempt,
                    )

                return result

            last_result = result

            logger.warning(
                (
                    "[Workflow %s] Tentativa %d/%d falhou "
                    "para %s: %s"
                ),
                workflow_id,
                attempt,
                MAX_ATTEMPTS,
                action.type,
                result.message,
            )

            if not result.retryable:
                logger.warning(
                    (
                        "[Workflow %s] Ação %s não permite "
                        "nova tentativa."
                    ),
                    workflow_id,
                    action.type,
                )

                break

            if attempt >= MAX_ATTEMPTS:
                logger.error(
                    (
                        "[Workflow %s] Limite de tentativas "
                        "atingido para %s."
                    ),
                    workflow_id,
                    action.type,
                )

                break

            logger.info(
                (
                    "[Workflow %s] Aguardando %.1fs "
                    "antes da próxima tentativa de %s."
                ),
                workflow_id,
                retry_delay,
                action.type,
            )

            time.sleep(retry_delay)

            if state is not None:
                state.throw_if_cancelled()

            retry_delay *= RETRY_BACKOFF_FACTOR

        if last_result is not None:
            return last_result

        return ExecutionResult.fail(
            action_type=action.type,
            message=(
                "A ação não produziu um resultado "
                f"válido: {action.type}"
            ),
            error_code="workflow_missing_result",
            retryable=False,
        )

    def _execute_action(
        self,
        action: Any,
    ) -> ExecutionResult:
        try:
            execution_results = self.executor.execute(
                [action]
            )

            if not execution_results:
                return ExecutionResult.fail(
                    action_type=action.type,
                    message=(
                        "O Executor não retornou resultado "
                        f"para a ação: {action.type}"
                    ),
                    error_code="executor_empty_result",
                    retryable=False,
                )

            return execution_results[0]

        except (
            TypeError,
            ValueError,
            RuntimeError,
        ) as error:
            logger.exception(
                "Erro inesperado na ação %s.",
                action.type,
            )

            return ExecutionResult.fail(
                action_type=action.type,
                message=(
                    "Erro inesperado durante "
                    f"a execução: {error}"
                ),
                error_code="workflow_unexpected_error",
                retryable=False,
            )

    def _handle_cancellation(
        self,
        *,
        state: WorkflowState,
        results: list[ExecutionResult],
        workflow_id: str,
        total_steps: int,
        workflow_started_at: float,
        active_task_id: str | None,
        active_action_type: str | None,
        error: WorkflowCancelledError,
    ) -> WorkflowResult:
        if active_task_id is not None:
            self.task_manager.cancel_task(active_task_id)

        snapshot = state.cancellation_snapshot()
        state.cancel(
            reason=snapshot.reason or error.reason,
            requested_by=snapshot.requested_by or error.requested_by,
        )

        state.context.add_history(
            "workflow_cancelled",
            workflow_id=workflow_id,
            action=active_action_type,
            reason=snapshot.reason or error.reason,
            requested_by=snapshot.requested_by or error.requested_by,
        )

        duration = time.perf_counter() - workflow_started_at
        logger.info(
            "[Workflow %s] Cancelado em %.2fs. Motivo: %s",
            workflow_id,
            duration,
            snapshot.reason or error.reason or "não informado",
        )

        return WorkflowResult.cancelled_result(
            completed_steps=len(state.completed_steps),
            total_steps=total_steps,
            results=results,
            reason=snapshot.reason or error.reason,
            requested_by=snapshot.requested_by or error.requested_by,
            cancelled_at=snapshot.cancelled_at,
            cancelled_step=active_action_type,
        )

    @staticmethod
    def _log_summary(
        *,
        workflow_id: str,
        state: WorkflowState,
        duration: float,
        success: bool,
    ) -> None:
        status = (
            "concluído"
            if success
            else "finalizado com falha"
        )

        logger.info(
            "[Workflow %s] %s em %.2fs.",
            workflow_id,
            status,
            duration,
        )

        logger.info(
            (
                "[Workflow %s] Concluídas: %d | "
                "Ignoradas: %d | Falhas: %d."
            ),
            workflow_id,
            len(state.completed_steps),
            len(state.skipped_steps),
            len(state.failed_steps),
        )
