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
from atlas.session.manager import SessionManager
from atlas.session.models import TimelineEventType
from atlas.session.resumption import (
    ResumptionRisk,
    ResumptionStatus,
    WorkflowResumptionPlanner,
)
from atlas.workflow.builder import WorkflowBuilder
from atlas.workflow.engine import WorkflowEngine


class StubPlanner:
    def __init__(self, actions: list[Action] | None = None) -> None:
        self.actions = list(actions or [])
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
        self.calls.append(list(actions))
        return self.handler(actions)


def make_manager(tmp_path: Path) -> SessionManager:
    return SessionManager(
        session_file=tmp_path / "last_session.json",
        database_path=tmp_path / "operational_sessions.db",
        user_id="Ssamir",
    )


def make_controller(
    tmp_path: Path,
    manager: SessionManager,
    *,
    planned_actions: list[Action] | None = None,
) -> tuple[AtlasController, StubExecutor, StubPlanner]:
    planner = StubPlanner(planned_actions)
    executor = StubExecutor(
        lambda actions: [
            ExecutionResult.ok(actions[0].type, "Etapa concluída.")
        ]
    )
    task_manager = TaskManager()
    kernel = SimpleNamespace(
        session=manager,
        scheduler_parser=SchedulerParser(),
        scheduler=Scheduler(tmp_path / "scheduler.json"),
        planner=planner,
        workflow_builder=WorkflowBuilder(),
        workflow_engine=WorkflowEngine(executor, task_manager),
        task_manager=task_manager,
    )
    return AtlasController(kernel), executor, planner


def record_interrupted_workflow(
    manager: SessionManager,
    workflow_id: str,
    actions: list[Action],
) -> None:
    manager.record_event(
        TimelineEventType.WORKFLOW_STARTED,
        f"Workflow iniciado com {len(actions)} etapa(s).",
        workflow_id=workflow_id,
        details={
            "plan_version": 1,
            "step_count": len(actions),
            "actions": WorkflowResumptionPlanner.serialize_actions(actions),
        },
    )


def test_plan_is_unavailable_without_interrupted_workflow(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)

    plan = manager.get_resumption_plan()

    assert plan.status is ResumptionStatus.NOT_AVAILABLE
    assert plan.can_resume is False
    assert plan.confirmation_token is None


def test_plan_skips_completed_steps_and_keeps_original_order(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    actions = [
        Action("helpdesk.diagnose", {"problem": "sem internet"}),
        Action("system.wait", {"seconds": 1}),
        Action("browser.page_title", {}),
    ]
    record_interrupted_workflow(manager, "workflow-safe", actions)
    manager.record_event(
        TimelineEventType.STEP_COMPLETED,
        "Diagnóstico concluído.",
        workflow_id="workflow-safe",
        action_type="helpdesk.diagnose",
        details={"step_index": 0, "step_number": 1},
    )

    plan = manager.get_resumption_plan()

    assert plan.status is ResumptionStatus.READY
    assert plan.completed_step_indexes == (0,)
    assert [step.step_index for step in plan.remaining_steps] == [1, 2]
    assert [action.type for action in plan.to_actions()] == [
        "system.wait",
        "browser.page_title",
    ]
    assert all(
        step.risk is ResumptionRisk.SAFE for step in plan.remaining_steps
    )


def test_external_state_change_requires_confirmation(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    record_interrupted_workflow(
        manager,
        "workflow-browser",
        [Action("browser.search", {"query": "Atlas"})],
    )

    plan = manager.get_resumption_plan()

    assert plan.status is ResumptionStatus.CONFIRMATION_REQUIRED
    assert plan.requires_confirmation is True
    assert plan.confirmation_token is not None
    assert len(plan.confirmation_token) == 20
    assert plan.remaining_steps[0].risk is (
        ResumptionRisk.CONFIRMATION_REQUIRED
    )


def test_destructive_and_redacted_actions_are_blocked(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    actions = [
        Action("file.delete", {"path": "relatorio.txt"}),
        Action("process.start", {"api_key": "segredo"}),
    ]
    serialized = WorkflowResumptionPlanner.serialize_actions(actions)

    assert serialized[1]["parameters"]["api_key"] == "[ATLAS_REDACTED]"

    record_interrupted_workflow(manager, "workflow-blocked", actions)
    plan = manager.get_resumption_plan()

    assert plan.status is ResumptionStatus.BLOCKED
    assert plan.can_resume is False
    assert plan.remaining_steps[0].risk is ResumptionRisk.BLOCKED
    assert plan.remaining_steps[1].risk is ResumptionRisk.BLOCKED


def test_legacy_workflow_without_serialized_actions_is_blocked(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    manager.record_event(
        TimelineEventType.WORKFLOW_STARTED,
        "Workflow antigo iniciado.",
        workflow_id="legacy",
        details={"action_types": ["browser.search"]},
    )

    plan = manager.get_resumption_plan()

    assert plan.status is ResumptionStatus.BLOCKED
    assert "plano de ações completo" in plan.reason


def test_controller_persists_plan_and_real_step_indexes(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    actions = [
        Action("helpdesk.diagnose", {"problem": "rede"}),
        Action("system.wait", {"seconds": 1}),
    ]
    controller, _, _ = make_controller(
        tmp_path,
        manager,
        planned_actions=actions,
    )

    controller.execute("diagnostique e aguarde")
    timeline = manager.get_timeline()
    started = next(
        event
        for event in timeline
        if event.event_type is TimelineEventType.WORKFLOW_STARTED
    )
    completed = [
        event
        for event in timeline
        if event.event_type is TimelineEventType.STEP_COMPLETED
    ]

    assert started.details["plan_version"] == 1
    assert started.details["actions"] == [
        {
            "type": "helpdesk.diagnose",
            "parameters": {"problem": "rede"},
        },
        {"type": "system.wait", "parameters": {"seconds": 1}},
    ]
    assert [event.details["step_index"] for event in completed] == [0, 1]
    assert [event.details["step_number"] for event in completed] == [1, 2]


def test_controller_resumes_only_pending_safe_steps_once(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    actions = [
        Action("helpdesk.diagnose", {"problem": "rede"}),
        Action("system.wait", {"seconds": 0}),
    ]
    record_interrupted_workflow(manager, "workflow-interrupted", actions)
    manager.record_event(
        TimelineEventType.STEP_COMPLETED,
        "Diagnóstico concluído.",
        workflow_id="workflow-interrupted",
        action_type="helpdesk.diagnose",
        details={"step_index": 0},
    )
    controller, executor, planner = make_controller(tmp_path, manager)

    resumed_actions, resumed_results = (
        controller.resume_interrupted_workflow()
    )
    duplicate_actions, duplicate_results = (
        controller.resume_interrupted_workflow()
    )

    assert resumed_actions == [Action("system.wait", {"seconds": 0})]
    assert resumed_results[0].success is True
    assert executor.calls == [[Action("system.wait", {"seconds": 0})]]
    assert planner.commands == []
    assert duplicate_actions == []
    assert duplicate_results[0].error_code == (
        "workflow_resume_not_available"
    )
    assert any(
        event.event_type is TimelineEventType.WORKFLOW_RESUMED
        and event.workflow_id == "workflow-interrupted"
        for event in manager.get_timeline()
    )


def test_controller_requires_valid_token_before_sensitive_resume(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    action = Action("browser.search", {"query": "carros usados"})
    record_interrupted_workflow(manager, "workflow-sensitive", [action])
    controller, executor, _ = make_controller(tmp_path, manager)
    plan = controller.get_resumption_plan()

    denied_actions, denied_results = controller.resume_interrupted_workflow(
        confirmation_token="token-incorreto"
    )

    assert denied_actions == []
    assert denied_results[0].error_code == (
        "workflow_resume_confirmation_required"
    )
    assert executor.calls == []
    assert controller.get_resumption_plan().confirmation_token == (
        plan.confirmation_token
    )

    resumed_actions, resumed_results = controller.resume_interrupted_workflow(
        confirmation_token=plan.confirmation_token
    )

    assert resumed_actions == [action]
    assert resumed_results[0].success is True
    assert executor.calls == [[action]]


def test_controller_never_executes_blocked_resume(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    record_interrupted_workflow(
        manager,
        "workflow-delete",
        [Action("file.delete", {"path": "dados.txt"})],
    )
    controller, executor, _ = make_controller(tmp_path, manager)

    actions, results = controller.resume_interrupted_workflow()

    assert actions == []
    assert results[0].error_code == "workflow_resume_blocked"
    assert executor.calls == []
    assert manager.get_timeline()[-1].event_type is (
        TimelineEventType.WORKFLOW_RESUME_BLOCKED
    )
