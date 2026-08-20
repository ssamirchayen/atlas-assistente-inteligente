from __future__ import annotations

from collections.abc import Callable
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.controller import AtlasController
from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.planner.task_manager import TaskManager
from atlas.scheduler.parser import SchedulerParser
from atlas.scheduler.scheduler import Scheduler
from atlas.session.manager import SessionManager
from atlas.session.models import TimelineEventType
from atlas.workflow.builder import WorkflowBuilder
from atlas.workflow.engine import WorkflowEngine


class StubPlanner:
    def __init__(self, actions: list[Action]) -> None:
        self.actions = actions

    def plan(self, _command: str) -> list[Action]:
        return list(self.actions)


class FailingPlanner:
    def plan(self, _command: str) -> list[Action]:
        raise RuntimeError("planejador indisponível")


class StubExecutor:
    def __init__(
        self,
        handler: Callable[[list[Action]], list[ExecutionResult]],
    ) -> None:
        self.handler = handler

    def execute(self, actions: list[Action]) -> list[ExecutionResult]:
        return self.handler(actions)


def make_manager(tmp_path: Path, *, user_id: str = "Ssamir") -> SessionManager:
    return SessionManager(
        session_file=tmp_path / f"{user_id}_last_session.json",
        database_path=tmp_path / "operational_sessions.db",
        user_id=user_id,
    )


def make_controller(
    tmp_path: Path,
    manager: SessionManager,
    *,
    actions: list[Action],
    handler: Callable[[list[Action]], list[ExecutionResult]],
) -> AtlasController:
    executor = StubExecutor(handler)
    task_manager = TaskManager()
    kernel = SimpleNamespace(
        session=manager,
        scheduler_parser=SchedulerParser(),
        scheduler=Scheduler(tmp_path / "scheduler.json"),
        planner=StubPlanner(actions),
        workflow_builder=WorkflowBuilder(),
        workflow_engine=WorkflowEngine(executor, task_manager),
        task_manager=task_manager,
    )
    return AtlasController(kernel)


def event_types(manager: SessionManager) -> list[TimelineEventType]:
    return [event.event_type for event in manager.get_timeline()]


def test_new_session_starts_timeline_in_utc(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    timeline = manager.get_timeline()

    assert len(timeline) == 1
    assert timeline[0].event_type is TimelineEventType.SESSION_STARTED
    assert timeline[0].sequence == 1
    assert timeline[0].occurred_at.tzinfo == timezone.utc
    assert timeline[0].session_id == manager.session_id


def test_events_survive_restart_and_keep_order(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    first = manager.record_event(
        TimelineEventType.COMMAND_RECEIVED,
        "Comando recebido.",
        workflow_id="workflow-1",
        details={"command": "abra o navegador"},
    )
    second = manager.record_event(
        TimelineEventType.STEP_COMPLETED,
        "Navegador aberto.",
        workflow_id="workflow-1",
        action_type="browser.open",
        details={"duration_seconds": 1.25},
    )

    restarted = make_manager(tmp_path)
    timeline = restarted.get_timeline()

    assert restarted.session_id == manager.session_id
    assert [event.sequence for event in timeline] == [1, 2, 3]
    assert [event.event_id for event in timeline[-2:]] == [
        first.event_id,
        second.event_id,
    ]
    assert timeline[-1].details["duration_seconds"] == 1.25
    assert timeline[-1].as_dict()["event_type"] == "step.completed"


def test_timeline_limit_returns_latest_events_chronologically(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)

    for index in range(5):
        manager.record_event(
            TimelineEventType.COMMAND_RECEIVED,
            f"Comando {index}.",
        )

    latest = manager.get_timeline(limit=2)
    latest_descending = manager.get_timeline(limit=2, newest_first=True)

    assert [event.sequence for event in latest] == [5, 6]
    assert [event.sequence for event in latest_descending] == [6, 5]


def test_timeline_supports_incremental_read(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.record_event(
        TimelineEventType.COMMAND_RECEIVED,
        "Primeiro comando.",
    )
    manager.record_event(
        TimelineEventType.COMMAND_COMPLETED,
        "Primeiro comando concluído.",
    )

    incremental = manager.get_timeline(after_sequence=2)

    assert [event.sequence for event in incremental] == [3]
    assert incremental[0].event_type is TimelineEventType.COMMAND_COMPLETED


def test_session_lifecycle_is_recorded(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    first_session_id = manager.session_id

    second = manager.start_new_session(title="Nova atividade")
    first_timeline = manager.get_timeline(session_id=first_session_id)
    manager.resume_session(first_session_id)
    second_timeline = manager.get_timeline(session_id=second.session_id)

    assert first_timeline[-1].event_type is TimelineEventType.SESSION_PAUSED
    assert second_timeline[-1].event_type is TimelineEventType.SESSION_PAUSED
    assert manager.get_timeline()[-1].event_type is (
        TimelineEventType.SESSION_RESUMED
    )


def test_user_cannot_read_another_users_timeline(tmp_path: Path) -> None:
    ssamir = make_manager(tmp_path, user_id="Ssamir")
    maria = make_manager(tmp_path, user_id="Maria")

    with pytest.raises(ValueError, match="outro usuário"):
        ssamir.get_timeline(session_id=maria.session_id)


def test_controller_records_successful_workflow(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    action = Action(type="browser.open", parameters={})
    result = ExecutionResult.ok(
        "browser.open",
        "Navegador aberto.",
        duration=0.4,
    )
    controller = make_controller(
        tmp_path,
        manager,
        actions=[action],
        handler=lambda _actions: [result],
    )

    actions, results = controller.execute("abra o navegador")
    timeline = manager.get_timeline()

    assert actions == [action]
    assert results == [result]
    assert event_types(manager)[-4:] == [
        TimelineEventType.COMMAND_RECEIVED,
        TimelineEventType.WORKFLOW_STARTED,
        TimelineEventType.STEP_COMPLETED,
        TimelineEventType.WORKFLOW_COMPLETED,
    ]
    workflow_ids = {event.workflow_id for event in timeline[-4:]}
    assert len(workflow_ids) == 1
    assert None not in workflow_ids
    assert timeline[-2].action_type == "browser.open"
    assert timeline[-2].details["duration_seconds"] == 0.4


def test_controller_records_step_and_workflow_failure(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    action = Action(type="browser.search", parameters={})
    failure = ExecutionResult.fail(
        "browser.search",
        "Pesquisa indisponível.",
        error_code="browser_unavailable",
    )
    controller = make_controller(
        tmp_path,
        manager,
        actions=[action],
        handler=lambda _actions: [failure],
    )

    controller.execute("pesquise carros usados")
    timeline = manager.get_timeline()

    assert event_types(manager)[-2:] == [
        TimelineEventType.STEP_FAILED,
        TimelineEventType.WORKFLOW_FAILED,
    ]
    assert timeline[-2].details["error_code"] == "browser_unavailable"


def test_controller_records_scheduled_and_unhandled_commands(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    controller = make_controller(
        tmp_path,
        manager,
        actions=[],
        handler=lambda _actions: [],
    )

    controller.execute("daqui a 2 minutos abra o navegador")
    controller.execute("converse comigo")

    types = event_types(manager)
    assert TimelineEventType.TASK_SCHEDULED in types
    assert TimelineEventType.COMMAND_COMPLETED in types
    assert types[-1] is TimelineEventType.COMMAND_UNHANDLED


def test_controller_records_unexpected_planner_failure(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    task_manager = TaskManager()
    kernel = SimpleNamespace(
        session=manager,
        scheduler_parser=SchedulerParser(),
        scheduler=Scheduler(tmp_path / "scheduler.json"),
        planner=FailingPlanner(),
        workflow_builder=WorkflowBuilder(),
        workflow_engine=WorkflowEngine(
            StubExecutor(lambda _actions: []),
            task_manager,
        ),
        task_manager=task_manager,
    )
    controller = AtlasController(kernel)

    with pytest.raises(RuntimeError, match="planejador indisponível"):
        controller.execute("execute uma ação")

    failed = manager.get_timeline()[-1]
    assert failed.event_type is TimelineEventType.COMMAND_FAILED
    assert failed.details["error_type"] == "RuntimeError"
