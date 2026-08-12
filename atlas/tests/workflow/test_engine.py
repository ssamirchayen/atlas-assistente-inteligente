from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.workflow.engine import MAX_ATTEMPTS, WorkflowEngine
from atlas.workflow.state import WorkflowState
from atlas.workflow.step import WorkflowStep


def make_action(
    action_type: str = "browser.open",
    **parameters: object,
) -> Action:
    return Action(
        type=action_type,
        parameters=dict(parameters),
    )


def make_step(
    action_type: str = "browser.open",
    **parameters: object,
) -> WorkflowStep:
    return WorkflowStep(
        action=make_action(
            action_type,
            **parameters,
        )
    )


def make_success(
    action_type: str = "browser.open",
    message: str = "Ação concluída.",
) -> ExecutionResult:
    return ExecutionResult.ok(
        action_type=action_type,
        message=message,
    )


def make_failure(
    action_type: str = "browser.open",
    message: str = "Ação falhou.",
    *,
    retryable: bool = False,
) -> ExecutionResult:
    return ExecutionResult.fail(
        action_type=action_type,
        message=message,
        error_code="test_error",
        retryable=retryable,
    )


@pytest.fixture
def executor() -> MagicMock:
    return MagicMock()


@pytest.fixture
def task_manager() -> MagicMock:
    manager = MagicMock()
    manager.create_task.return_value = SimpleNamespace(id="task-1")
    return manager


@pytest.fixture
def engine(
    executor: MagicMock,
    task_manager: MagicMock,
) -> WorkflowEngine:
    return WorkflowEngine(
        executor=executor,
        task_manager=task_manager,
    )


def test_execute_empty_workflow_returns_success(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    state = WorkflowState(steps=[])

    result = engine.execute(state)

    assert result.success is True
    assert result.failed is False
    assert result.completed_steps == 0
    assert result.total_steps == 0
    assert result.progress == 1.0
    assert result.results == []

    executor.execute.assert_not_called()
    task_manager.create_task.assert_not_called()


def test_execute_single_step_success(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    step = make_step(
        "browser.open",
        url="https://example.com",
    )
    state = WorkflowState(steps=[step])
    execution_result = make_success(
        action_type="browser.open",
        message="Site aberto.",
    )
    executor.execute.return_value = [execution_result]

    result = engine.execute(state)

    assert result.success is True
    assert result.completed_steps == 1
    assert result.total_steps == 1
    assert result.results == [execution_result]

    assert state.finished is True
    assert state.failed is False
    assert state.completed_steps == [step]
    assert state.skipped_steps == []
    assert state.failed_steps == []
    assert state.current_index == 1

    executor.execute.assert_called_once_with([step.action])
    task_manager.create_task.assert_called_once_with(
        description="browser.open",
        action=step.action,
    )
    task_manager.start_task.assert_called_once_with("task-1")
    task_manager.complete_task.assert_called_once_with(
        "task-1",
        execution_result,
    )
    task_manager.fail_task.assert_not_called()


def test_execute_multiple_steps_success(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    first_step = make_step("browser.open")
    second_step = make_step("mouse.click")
    third_step = make_step("keyboard.press")

    first_result = make_success("browser.open")
    second_result = make_success("mouse.click")
    third_result = make_success("keyboard.press")

    executor.execute.side_effect = [
        [first_result],
        [second_result],
        [third_result],
    ]
    task_manager.create_task.side_effect = [
        SimpleNamespace(id="task-1"),
        SimpleNamespace(id="task-2"),
        SimpleNamespace(id="task-3"),
    ]

    state = WorkflowState(
        steps=[
            first_step,
            second_step,
            third_step,
        ]
    )

    result = engine.execute(state)

    assert result.success is True
    assert result.completed_steps == 3
    assert result.total_steps == 3
    assert result.results == [
        first_result,
        second_result,
        third_result,
    ]
    assert state.completed_steps == [
        first_step,
        second_step,
        third_step,
    ]
    assert state.progress == 1.0

    assert executor.execute.call_args_list == [
        call([first_step.action]),
        call([second_step.action]),
        call([third_step.action]),
    ]
    assert task_manager.complete_task.call_count == 3
    task_manager.fail_task.assert_not_called()


def test_execute_skips_step_when_condition_is_false(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    action = make_action("browser.open")
    step = MagicMock()
    step.action = action
    step.should_execute.return_value = False

    state = WorkflowState(steps=[step])

    result = engine.execute(state)

    assert result.success is True
    assert result.completed_steps == 0
    assert result.total_steps == 0
    assert result.results == []

    assert state.finished is True
    assert state.completed_steps == []
    assert state.skipped_steps == [step]
    assert state.failed_steps == []
    assert state.progress == 1.0

    step.should_execute.assert_called_once_with(state.context.data)
    executor.execute.assert_not_called()
    task_manager.create_task.assert_not_called()


def test_execute_continues_after_skipped_step(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    skipped_action = make_action("browser.skip")
    skipped_step = MagicMock()
    skipped_step.action = skipped_action
    skipped_step.should_execute.return_value = False

    executed_step = make_step("browser.open")
    execution_result = make_success("browser.open")
    executor.execute.return_value = [execution_result]

    state = WorkflowState(
        steps=[
            skipped_step,
            executed_step,
        ]
    )

    result = engine.execute(state)

    assert result.success is True
    assert result.completed_steps == 1
    assert result.total_steps == 1
    assert result.results == [execution_result]
    assert state.skipped_steps == [skipped_step]
    assert state.completed_steps == [executed_step]
    assert state.finished is True


def test_execute_non_retryable_failure_stops_workflow(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    first_step = make_step("browser.open")
    second_step = make_step("mouse.click")
    failed_result = make_failure(
        action_type="browser.open",
        message="Não foi possível abrir o site.",
        retryable=False,
    )
    executor.execute.return_value = [failed_result]

    state = WorkflowState(
        steps=[
            first_step,
            second_step,
        ]
    )

    result = engine.execute(state)

    assert result.success is False
    assert result.failed is True
    assert result.completed_steps == 0
    assert result.total_steps == 2
    assert result.results == [failed_result]
    assert result.error == failed_result.message

    assert state.failed is True
    assert state.finished is True
    assert state.error == failed_result.message
    assert state.failed_steps == [first_step]
    assert state.completed_steps == []
    assert state.current_index == 0

    executor.execute.assert_called_once_with([first_step.action])
    task_manager.fail_task.assert_called_once_with(
        "task-1",
        failed_result,
    )
    task_manager.complete_task.assert_not_called()


def test_execute_stops_after_failure_of_later_step(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    first_step = make_step("browser.open")
    second_step = make_step("mouse.click")
    third_step = make_step("keyboard.press")

    first_result = make_success("browser.open")
    failed_result = make_failure(
        "mouse.click",
        retryable=False,
    )

    executor.execute.side_effect = [
        [first_result],
        [failed_result],
    ]
    task_manager.create_task.side_effect = [
        SimpleNamespace(id="task-1"),
        SimpleNamespace(id="task-2"),
    ]

    state = WorkflowState(
        steps=[
            first_step,
            second_step,
            third_step,
        ]
    )

    result = engine.execute(state)

    assert result.success is False
    assert result.completed_steps == 1
    assert result.total_steps == 3
    assert result.results == [
        first_result,
        failed_result,
    ]

    assert state.completed_steps == [first_step]
    assert state.failed_steps == [second_step]
    assert third_step not in state.completed_steps
    assert executor.execute.call_count == 2

    task_manager.complete_task.assert_called_once_with(
        "task-1",
        first_result,
    )
    task_manager.fail_task.assert_called_once_with(
        "task-2",
        failed_result,
    )


def test_retryable_failure_succeeds_on_second_attempt(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    step = make_step("browser.open")
    first_result = make_failure(
        "browser.open",
        message="Falha temporária.",
        retryable=True,
    )
    second_result = make_success(
        "browser.open",
        message="Ação concluída na segunda tentativa.",
    )
    executor.execute.side_effect = [
        [first_result],
        [second_result],
    ]

    state = WorkflowState(steps=[step])

    with patch("atlas.workflow.engine.time.sleep") as sleep_mock:
        result = engine.execute(state)

    assert result.success is True
    assert result.results == [second_result]
    assert state.completed_steps == [step]
    assert executor.execute.call_count == 2
    sleep_mock.assert_called_once_with(1.0)
    task_manager.complete_task.assert_called_once_with(
        "task-1",
        second_result,
    )


def test_retry_uses_exponential_backoff(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    action = make_action("browser.open")
    first_result = make_failure(
        "browser.open",
        retryable=True,
    )
    second_result = make_failure(
        "browser.open",
        retryable=True,
    )
    third_result = make_success("browser.open")

    executor.execute.side_effect = [
        [first_result],
        [second_result],
        [third_result],
    ]

    with patch("atlas.workflow.engine.time.sleep") as sleep_mock:
        result = engine._execute_with_retry(
            action=action,
            workflow_id="workflow",
            step_number=1,
            total_steps=1,
        )

    assert result is third_result
    assert executor.execute.call_count == 3
    assert sleep_mock.call_args_list == [
        call(1.0),
        call(2.0),
    ]


def test_retry_stops_after_maximum_attempts(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    action = make_action("browser.open")
    failures = [
        make_failure(
            "browser.open",
            message=f"Falha {index}.",
            retryable=True,
        )
        for index in range(1, MAX_ATTEMPTS + 1)
    ]
    executor.execute.side_effect = [
        [failure]
        for failure in failures
    ]

    with patch("atlas.workflow.engine.time.sleep") as sleep_mock:
        result = engine._execute_with_retry(
            action=action,
            workflow_id="workflow",
            step_number=1,
            total_steps=1,
        )

    assert result is failures[-1]
    assert executor.execute.call_count == MAX_ATTEMPTS
    assert sleep_mock.call_args_list == [
        call(1.0),
        call(2.0),
    ]


def test_non_retryable_failure_does_not_sleep(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    action = make_action("browser.open")
    failure = make_failure(
        "browser.open",
        retryable=False,
    )
    executor.execute.return_value = [failure]

    with patch("atlas.workflow.engine.time.sleep") as sleep_mock:
        result = engine._execute_with_retry(
            action=action,
            workflow_id="workflow",
            step_number=1,
            total_steps=1,
        )

    assert result is failure
    executor.execute.assert_called_once_with([action])
    sleep_mock.assert_not_called()


def test_execute_action_returns_first_executor_result(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    action = make_action("browser.open")
    first_result = make_success("browser.open")
    second_result = make_success("browser.other")
    executor.execute.return_value = [
        first_result,
        second_result,
    ]

    result = engine._execute_action(action)

    assert result is first_result
    executor.execute.assert_called_once_with([action])


def test_execute_action_handles_empty_executor_result(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    action = make_action("browser.open")
    executor.execute.return_value = []

    result = engine._execute_action(action)

    assert result.success is False
    assert result.action_type == "browser.open"
    assert result.error_code == "executor_empty_result"
    assert result.retryable is False
    assert "não retornou resultado" in result.message


@pytest.mark.parametrize(
    ("exception", "expected_text"),
    [
        (TypeError("tipo inválido"), "tipo inválido"),
        (ValueError("valor inválido"), "valor inválido"),
        (RuntimeError("falha de execução"), "falha de execução"),
    ],
)
def test_execute_action_converts_expected_exception_to_failure(
    engine: WorkflowEngine,
    executor: MagicMock,
    exception: Exception,
    expected_text: str,
) -> None:
    action = make_action("browser.open")
    executor.execute.side_effect = exception

    result = engine._execute_action(action)

    assert result.success is False
    assert result.action_type == "browser.open"
    assert result.error_code == "workflow_unexpected_error"
    assert result.retryable is False
    assert expected_text in result.message


def test_execute_action_does_not_hide_unhandled_exception(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    action = make_action("browser.open")
    executor.execute.side_effect = KeyError("erro inesperado")

    with pytest.raises(KeyError, match="erro inesperado"):
        engine._execute_action(action)


def test_context_receives_successful_result(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    step = make_step("browser.open")
    execution_result = make_success("browser.open")
    executor.execute.return_value = [execution_result]
    state = WorkflowState(steps=[step])

    engine.execute(state)

    assert state.context.last_result() is execution_result


def test_skipped_step_is_added_to_context_history(
    engine: WorkflowEngine,
) -> None:
    action = make_action("browser.skip")
    step = MagicMock()
    step.action = action
    step.should_execute.return_value = False
    state = WorkflowState(steps=[step])

    engine.execute(state)

    assert state.context.history
    history_entry = state.context.history[-1]
    assert history_entry["event"] == "step_skipped"
    assert history_entry["action"] == "browser.skip"
    assert "workflow_id" in history_entry


def test_successful_step_is_added_to_context_history(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    step = make_step("browser.open")
    executor.execute.return_value = [make_success("browser.open")]
    state = WorkflowState(steps=[step])

    engine.execute(state)

    assert state.context.history
    history_entry = state.context.history[-1]
    assert history_entry["event"] == "step_completed"
    assert history_entry["action"] == "browser.open"
    assert history_entry["success"] is True
    assert "duration" in history_entry
    assert "workflow_id" in history_entry


def test_failed_step_is_added_to_context_history(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    step = make_step("browser.open")
    executor.execute.return_value = [
        make_failure(
            "browser.open",
            retryable=False,
        )
    ]
    state = WorkflowState(steps=[step])

    engine.execute(state)

    assert state.context.history
    history_entry = state.context.history[-1]
    assert history_entry["event"] == "step_failed"
    assert history_entry["action"] == "browser.open"
    assert history_entry["success"] is False


def test_task_is_started_before_executor_runs(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    step = make_step("browser.open")
    execution_result = make_success("browser.open")
    calls: list[str] = []

    task_manager.start_task.side_effect = (
        lambda task_id: calls.append("start")
    )
    executor.execute.side_effect = (
        lambda actions: (
            calls.append("execute")
            or [execution_result]
        )
    )

    state = WorkflowState(steps=[step])
    engine.execute(state)

    assert calls == [
        "start",
        "execute",
    ]


def test_log_summary_is_called_for_success(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    step = make_step("browser.open")
    executor.execute.return_value = [make_success("browser.open")]
    state = WorkflowState(steps=[step])

    with patch.object(engine, "_log_summary") as summary_mock:
        engine.execute(state)

    summary_mock.assert_called_once()
    assert summary_mock.call_args.kwargs["state"] is state
    assert summary_mock.call_args.kwargs["success"] is True
    assert summary_mock.call_args.kwargs["duration"] >= 0.0


def test_log_summary_is_called_for_failure(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    step = make_step("browser.open")
    executor.execute.return_value = [
        make_failure(
            "browser.open",
            retryable=False,
        )
    ]
    state = WorkflowState(steps=[step])

    with patch.object(engine, "_log_summary") as summary_mock:
        engine.execute(state)

    summary_mock.assert_called_once()
    assert summary_mock.call_args.kwargs["state"] is state
    assert summary_mock.call_args.kwargs["success"] is False


def test_execute_uses_different_task_ids(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    first_step = make_step("browser.open")
    second_step = make_step("mouse.click")
    first_result = make_success("browser.open")
    second_result = make_success("mouse.click")

    executor.execute.side_effect = [
        [first_result],
        [second_result],
    ]
    task_manager.create_task.side_effect = [
        SimpleNamespace(id="first-task"),
        SimpleNamespace(id="second-task"),
    ]

    state = WorkflowState(
        steps=[
            first_step,
            second_step,
        ]
    )

    engine.execute(state)

    assert task_manager.start_task.call_args_list == [
        call("first-task"),
        call("second-task"),
    ]
    assert task_manager.complete_task.call_args_list == [
        call("first-task", first_result),
        call("second-task", second_result),
    ]


def test_result_compatibility_properties_after_success(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    step = make_step("browser.open")
    executor.execute.return_value = [make_success("browser.open")]
    state = WorkflowState(steps=[step])

    result = engine.execute(state)

    assert result.completed_actions == 1
    assert result.total_actions == 1
    assert result.is_complete is True


def test_result_progress_after_partial_failure(
    engine: WorkflowEngine,
    executor: MagicMock,
    task_manager: MagicMock,
) -> None:
    first_step = make_step("browser.open")
    second_step = make_step("mouse.click")
    first_result = make_success("browser.open")
    second_result = make_failure(
        "mouse.click",
        retryable=False,
    )

    executor.execute.side_effect = [
        [first_result],
        [second_result],
    ]
    task_manager.create_task.side_effect = [
        SimpleNamespace(id="task-1"),
        SimpleNamespace(id="task-2"),
    ]

    state = WorkflowState(
        steps=[
            first_step,
            second_step,
        ]
    )

    result = engine.execute(state)

    assert result.progress == pytest.approx(0.5)
    assert result.is_complete is False


def test_execute_with_retry_returns_success_without_sleep(
    engine: WorkflowEngine,
    executor: MagicMock,
) -> None:
    action = make_action("browser.open")
    success = make_success("browser.open")
    executor.execute.return_value = [success]

    with patch("atlas.workflow.engine.time.sleep") as sleep_mock:
        result = engine._execute_with_retry(
            action=action,
            workflow_id="workflow",
            step_number=1,
            total_steps=1,
        )

    assert result is success
    executor.execute.assert_called_once_with([action])
    sleep_mock.assert_not_called()
