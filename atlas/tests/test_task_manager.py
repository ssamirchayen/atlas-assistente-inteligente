from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.planner.task import TaskStatus
from atlas.planner.task_manager import TaskManager


def test_task_lifecycle_completed() -> None:
    manager = TaskManager()

    action = Action(
        type="file.create_folder",
        parameters={
            "path": "Estudos",
        },
    )

    task = manager.create_task(
        description=action.type,
        action=action,
    )

    assert task.status == TaskStatus.PENDING
    assert manager.total == 1
    assert manager.pending == 1

    manager.start_task(task.id)

    assert task.status == TaskStatus.RUNNING
    assert task.started_at is not None
    assert manager.running == 1

    result = ExecutionResult.ok(
        action_type=action.type,
        message="Pasta criada com sucesso.",
    )

    manager.complete_task(
        task.id,
        result,
    )

    assert task.status == TaskStatus.COMPLETED
    assert task.result is result
    assert task.finished_at is not None
    assert manager.completed == 1
    assert manager.progress == 100.0


def test_task_lifecycle_failed() -> None:
    manager = TaskManager()

    task = manager.create_task(
        description="process.start",
    )

    manager.start_task(task.id)

    result = ExecutionResult.fail(
        action_type="process.start",
        message="Programa não encontrado.",
        error_code="program_not_found",
        retryable=False,
    )

    manager.fail_task(
        task.id,
        result,
    )

    assert task.status == TaskStatus.FAILED
    assert task.result is result
    assert manager.failed == 1
    assert manager.progress == 100.0


def test_cancel_task() -> None:
    manager = TaskManager()

    task = manager.create_task(
        description="browser.open",
    )

    manager.cancel_task(task.id)

    assert task.status == TaskStatus.CANCELLED
    assert task.finished_at is not None
    assert manager.cancelled == 1
    assert manager.progress == 100.0


def test_unknown_task_raises_key_error() -> None:
    manager = TaskManager()

    try:
        manager.start_task("id-inexistente")

    except KeyError as error:
        assert "id-inexistente" in str(error)

    else:
        raise AssertionError(
            "Era esperado um KeyError."
        )