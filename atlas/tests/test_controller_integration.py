from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from atlas.core.controller import AtlasController
from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.planner.task_manager import TaskManager
from atlas.scheduler.parser import SchedulerParser
from atlas.scheduler.scheduler import Scheduler
from atlas.workflow.builder import WorkflowBuilder
from atlas.workflow.engine import WorkflowEngine


class StubPlanner:
    def __init__(self, actions: list[Action]) -> None:
        self.actions = actions
        self.commands: list[str] = []

    def plan(self, command: str) -> list[Action]:
        self.commands.append(command)
        return list(self.actions)


class StubExecutor:
    def __init__(
        self,
        handler: Callable[[list[Action]], list[ExecutionResult]],
    ) -> None:
        self.handler = handler
        self.calls: list[list[Action]] = []

    def execute(self, actions: list[Action]) -> list[ExecutionResult]:
        self.calls.append(actions)
        return self.handler(actions)


def make_action(action_type: str) -> Action:
    return Action(type=action_type, parameters={})


def make_controller(
    tmp_path: Path,
    actions: list[Action],
    handler: Callable[[list[Action]], list[ExecutionResult]],
) -> tuple[AtlasController, SimpleNamespace, StubPlanner, StubExecutor]:
    planner = StubPlanner(actions)
    executor = StubExecutor(handler)
    task_manager = TaskManager()
    kernel = SimpleNamespace(
        scheduler_parser=SchedulerParser(),
        scheduler=Scheduler(tmp_path / "scheduler.json"),
        planner=planner,
        workflow_builder=WorkflowBuilder(),
        workflow_engine=WorkflowEngine(executor, task_manager),
        task_manager=task_manager,
    )
    return AtlasController(kernel), kernel, planner, executor


def test_controller_executes_complete_pipeline_successfully(
    tmp_path: Path,
) -> None:
    action = make_action("browser.open")
    success = ExecutionResult.ok("browser.open", "Site aberto.")
    controller, kernel, planner, executor = make_controller(
        tmp_path,
        [action],
        lambda _: [success],
    )

    actions, results = controller.execute("abra o navegador")

    assert actions == [action]
    assert results == [success]
    assert planner.commands == ["abra o navegador"]
    assert executor.calls == [[action]]
    assert kernel.task_manager.completed == 1
    assert controller.active_workflow is None


def test_controller_executes_multiple_actions_in_order(tmp_path: Path) -> None:
    actions = [make_action("browser.open"), make_action("browser.search")]

    def succeed(received: list[Action]) -> list[ExecutionResult]:
        return [ExecutionResult.ok(received[0].type, "Concluída.")]

    controller, kernel, _, executor = make_controller(
        tmp_path,
        actions,
        succeed,
    )

    planned, results = controller.execute("abra e pesquise")

    assert planned == actions
    assert [call[0].type for call in executor.calls] == [
        "browser.open",
        "browser.search",
    ]
    assert len(results) == 2
    assert all(result.success for result in results)
    assert kernel.task_manager.completed == 2


def test_controller_propagates_workflow_failure(tmp_path: Path) -> None:
    actions = [make_action("browser.open"), make_action("browser.search")]
    failure = ExecutionResult.fail(
        "browser.open",
        "Navegador indisponível.",
        error_code="browser_unavailable",
        retryable=False,
    )
    controller, kernel, _, executor = make_controller(
        tmp_path,
        actions,
        lambda _: [failure],
    )

    _, results = controller.execute("abra e pesquise")

    assert results == [failure]
    assert len(executor.calls) == 1
    assert kernel.task_manager.failed == 1
    assert controller.active_workflow is None


def test_controller_returns_empty_when_planner_has_no_actions(
    tmp_path: Path,
) -> None:
    controller, kernel, planner, executor = make_controller(
        tmp_path,
        [],
        lambda _: [],
    )

    actions, results = controller.execute("converse comigo")

    assert actions == []
    assert results == []
    assert planner.commands == ["converse comigo"]
    assert executor.calls == []
    assert kernel.task_manager.total == 0


def test_controller_schedules_without_calling_planner(tmp_path: Path) -> None:
    controller, kernel, planner, executor = make_controller(
        tmp_path,
        [make_action("browser.open")],
        lambda _: [],
    )

    actions, results = controller.execute(
        "Atlas daqui a 2 minutos abra o navegador"
    )

    assert actions == []
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].action_type == "scheduler"
    assert kernel.scheduler.total == 1
    assert planner.commands == []
    assert executor.calls == []


def test_controller_cancels_active_workflow_and_reports_result(
    tmp_path: Path,
) -> None:
    action = make_action("browser.open")
    controller: AtlasController

    def cancel_during_action(_: list[Action]) -> list[ExecutionResult]:
        changed = controller.cancel_active_workflow(
            reason="Solicitado pelo usuário",
            requested_by="Ssamir",
        )
        assert changed is True
        return [ExecutionResult.ok("browser.open", "Ação encerrada.")]

    controller, kernel, _, executor = make_controller(
        tmp_path,
        [action],
        cancel_during_action,
    )

    actions, results = controller.execute("abra o navegador")

    assert actions == [action]
    assert len(results) == 1
    cancellation = results[0]
    assert cancellation.success is False
    assert cancellation.error_code == "workflow_cancelled"
    assert "Solicitado pelo usuário" in cancellation.message
    assert cancellation.data["requested_by"] == "Ssamir"
    assert kernel.task_manager.cancelled == 1
    assert executor.calls == [[action]]
    assert controller.active_workflow is None


def test_cancel_returns_false_without_active_workflow(tmp_path: Path) -> None:
    controller, _, _, _ = make_controller(tmp_path, [], lambda _: [])

    assert controller.cancel_active_workflow(reason="Nada ativo") is False
