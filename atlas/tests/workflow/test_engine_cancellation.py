from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.workflow.engine import WorkflowEngine
from atlas.workflow.state import WorkflowState
from atlas.workflow.step import WorkflowStep


def make_state(*action_types: str) -> WorkflowState:
    return WorkflowState(
        steps=[
            WorkflowStep(action=Action(type=action_type, parameters={}))
            for action_type in action_types
        ]
    )


def make_engine() -> tuple[WorkflowEngine, MagicMock, MagicMock]:
    executor = MagicMock()
    task_manager = MagicMock()
    task_manager.create_task.return_value = SimpleNamespace(id="task-1")
    return WorkflowEngine(executor, task_manager), executor, task_manager


def test_cancel_before_start_does_not_create_task() -> None:
    engine, executor, task_manager = make_engine()
    state = make_state("browser.open")
    state.cancel(reason="Solicitado pelo usuário", requested_by="Ssamir")

    result = engine.execute(state)

    assert result.cancelled is True
    assert result.success is False
    assert result.cancellation_reason == "Solicitado pelo usuário"
    assert result.cancellation_requested_by == "Ssamir"
    assert result.cancelled_step is None
    assert result.completed_steps == 0
    executor.execute.assert_not_called()
    task_manager.create_task.assert_not_called()


def test_cancel_during_execution_cancels_active_task() -> None:
    engine, executor, task_manager = make_engine()
    state = make_state("browser.open", "browser.search")

    def execute_and_cancel(actions: list[Action]) -> list[ExecutionResult]:
        state.cancel(reason="Interromper automação", requested_by="Ssamir")
        return [ExecutionResult.ok(actions[0].type, "Ação finalizada com segurança.")]

    executor.execute.side_effect = execute_and_cancel
    result = engine.execute(state)

    assert result.cancelled is True
    assert result.cancelled_step == "browser.open"
    assert result.completed_steps == 0
    assert state.finished is True
    assert state.cancelled is True
    executor.execute.assert_called_once()
    task_manager.cancel_task.assert_called_once_with("task-1")
    task_manager.complete_task.assert_not_called()
    task_manager.fail_task.assert_not_called()


def test_cancel_between_steps_prevents_next_action() -> None:
    engine, executor, task_manager = make_engine()
    state = make_state("browser.open", "browser.search")
    first_result = ExecutionResult.ok("browser.open", "Site aberto.")

    def complete_then_cancel(actions: list[Action]) -> list[ExecutionResult]:
        if actions[0].type == "browser.open":
            return [first_result]
        raise AssertionError("A segunda etapa não deveria executar.")

    executor.execute.side_effect = complete_then_cancel
    task_manager.complete_task.side_effect = lambda *_: state.cancel(
        reason="Parar após a primeira etapa",
        requested_by="painel",
    )

    result = engine.execute(state)

    assert result.cancelled is True
    assert result.completed_steps == 1
    assert result.results == [first_result]
    assert executor.execute.call_count == 1


def test_cancel_before_retry_does_not_sleep_or_retry() -> None:
    engine, executor, task_manager = make_engine()
    state = make_state("browser.open")
    failure = ExecutionResult.fail(
        "browser.open",
        "Falha temporária.",
        error_code="temporary",
        retryable=True,
    )

    def fail_and_cancel(_: list[Action]) -> list[ExecutionResult]:
        state.cancel(reason="Cancelar retry", requested_by="Ssamir")
        return [failure]

    executor.execute.side_effect = fail_and_cancel

    with patch("atlas.workflow.engine.time.sleep") as sleep_mock:
        result = engine.execute(state)

    assert result.cancelled is True
    assert executor.execute.call_count == 1
    sleep_mock.assert_not_called()
    task_manager.cancel_task.assert_called_once_with("task-1")


def test_cancelled_execution_is_recorded_in_history() -> None:
    engine, _, _ = make_engine()
    state = make_state("browser.open")
    state.cancel(reason="Teste", requested_by="pytest")

    engine.execute(state)

    entry = state.context.history[-1]
    assert entry["event"] == "workflow_cancelled"
    assert entry["reason"] == "Teste"
    assert entry["requested_by"] == "pytest"
