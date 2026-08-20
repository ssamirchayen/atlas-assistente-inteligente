from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from atlas.gui.service import AtlasGuiService, SerialCommandRunner
from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.session.models import (
    OperationalEvent,
    OperationalSession,
    SessionStatus,
    TimelineEventType,
)
from atlas.session.resumption import ResumptionPlan


def make_service(
    *,
    actions: list[Action] | None = None,
    results: list[ExecutionResult] | None = None,
    route_handled: bool = False,
) -> tuple[AtlasGuiService, MagicMock, SimpleNamespace]:
    controller = MagicMock()
    controller.execute.return_value = (actions or [], results or [])
    controller.cancel_active_workflow.return_value = True

    context = MagicMock()
    context.get_recent_history.return_value = "conversa recente"
    memory = MagicMock()
    memory.context.return_value = "memória relevante"
    router = MagicMock()
    router.route_priority.return_value = SimpleNamespace(
        handled=False,
        message="",
    )
    router.route.return_value = SimpleNamespace(
        handled=route_handled,
        message="Skill executada.",
    )
    brain = MagicMock()
    brain.respond.return_value = "Resposta do cérebro."
    auto_memory = MagicMock()
    kernel = SimpleNamespace(
        context=context,
        memory=memory,
        router=router,
        brain=brain,
        auto_memory=auto_memory,
        session=MagicMock(),
    )

    service = AtlasGuiService(
        kernel=kernel,
        controller=controller,
        enable_scheduler=False,
    )
    return service, controller, kernel


def test_service_uses_controller_for_workflow() -> None:
    action = Action(type="browser.open", parameters={})
    execution = ExecutionResult.ok("browser.open", "Navegador aberto.")
    service, controller, kernel = make_service(
        actions=[action],
        results=[execution],
    )

    result = service.execute("abra o navegador")

    assert result.message == "Navegador aberto."
    assert result.source == "workflow"
    assert result.success is True
    assert result.action_count == 1
    controller.execute.assert_called_once_with("abra o navegador")
    kernel.router.route.assert_not_called()
    kernel.brain.respond.assert_not_called()


def test_memory_command_is_handled_before_planner() -> None:
    action = Action(type="browser.search", parameters={"query": "pudim"})
    execution = ExecutionResult.ok(
        "browser.search",
        "Pesquisei no Google por: pudim",
    )
    service, controller, kernel = make_service(
        actions=[action],
        results=[execution],
    )
    kernel.router.route_priority.return_value = SimpleNamespace(
        handled=True,
        message="Lembrei que sua sobremesa favorita é pudim de cupuaçu.",
    )

    result = service.execute(
        "Atlas, lembre que minha sobremesa favorita é pudim de cupuaçu"
    )

    assert result.source == "skill"
    assert "sobremesa favorita" in result.message
    controller.execute.assert_not_called()
    kernel.router.route.assert_not_called()
    kernel.brain.respond.assert_not_called()


def test_service_removes_optional_wake_word_before_planning() -> None:
    action = Action(
        type="browser.click_first_result",
        parameters={},
    )
    execution = ExecutionResult.ok(
        "browser.click_first_result",
        "Cliquei no primeiro resultado.",
    )
    service, controller, kernel = make_service(
        actions=[action],
        results=[execution],
    )

    result = service.execute(
        "Atlas, click no primeiro resultado da pesquisa anterior"
    )

    assert result.success is True
    controller.execute.assert_called_once_with(
        "click no primeiro resultado da pesquisa anterior"
    )
    kernel.context.add_turn.assert_called_once_with(
        "Atlas, click no primeiro resultado da pesquisa anterior",
        "Cliquei no primeiro resultado.",
    )


def test_service_handles_wake_word_without_command() -> None:
    service, controller, _ = make_service()

    result = service.execute("Atlas")

    assert result.source == "system"
    assert result.success is False
    controller.execute.assert_not_called()


def test_service_reports_scheduled_command() -> None:
    scheduled = ExecutionResult.ok("scheduler", "Tarefa agendada.")
    service, _, _ = make_service(results=[scheduled])

    result = service.execute("daqui a 2 minutos abra o navegador")

    assert result.source == "scheduler"
    assert result.action_count == 0
    assert result.message == "Tarefa agendada."


def test_service_uses_skill_before_chat_fallback() -> None:
    service, _, kernel = make_service(route_handled=True)

    result = service.execute("comando de uma skill")

    assert result.source == "skill"
    assert result.message == "Skill executada."
    kernel.brain.respond.assert_not_called()
    kernel.context.add_turn.assert_called_once_with(
        "comando de uma skill",
        "Skill executada.",
    )


def test_service_uses_brain_as_final_fallback() -> None:
    service, _, kernel = make_service()

    result = service.execute("como você está?")

    assert result.source == "brain"
    assert result.message == "Resposta do cérebro."
    kernel.brain.respond.assert_called_once_with(
        "como você está?",
        "memória relevante\n\nconversa recente",
    )
    kernel.auto_memory.capture.assert_called_once_with("como você está?")


def test_automatic_memory_failure_does_not_break_response() -> None:
    service, _, kernel = make_service()
    kernel.auto_memory.capture.side_effect = RuntimeError("banco ocupado")

    result = service.execute("eu moro em Manaus")

    assert result.success is True
    assert result.message == "Resposta do cérebro."
    kernel.context.add_turn.assert_called_once()


def test_service_propagates_cancellation() -> None:
    cancelled = ExecutionResult.fail(
        "workflow",
        "Workflow cancelado.",
        error_code="workflow_cancelled",
        retryable=False,
    )
    service, controller, _ = make_service(results=[cancelled])

    result = service.execute("abra o navegador")

    assert result.cancelled is True
    assert result.success is False
    assert service.cancel() is True
    controller.cancel_active_workflow.assert_called_once_with(
        reason="Cancelado pela interface",
        requested_by="Ssamir",
    )


def test_service_handles_exit_without_calling_controller() -> None:
    service, controller, _ = make_service()

    result = service.execute("encerrar atlas")

    assert result.should_close is True
    assert result.source == "system"
    controller.execute.assert_not_called()


def test_serial_runner_reuses_the_same_thread() -> None:
    thread_ids: list[int] = []

    def handler(command: str):
        thread_ids.append(threading.get_ident())
        return command.upper()

    runner = SerialCommandRunner(handler)

    first = runner.submit("primeiro").result(timeout=2)
    second = runner.submit("segundo").result(timeout=2)
    runner.close()

    assert first == "PRIMEIRO"
    assert second == "SEGUNDO"
    assert len(set(thread_ids)) == 1


def test_serial_runner_runs_cleanup_on_command_thread() -> None:
    thread_ids: list[int] = []
    cleanup_finished = threading.Event()

    def handler(command: str):
        thread_ids.append(threading.get_ident())
        return command

    def cleanup() -> None:
        thread_ids.append(threading.get_ident())
        cleanup_finished.set()

    runner = SerialCommandRunner(handler)
    runner.submit("comando").result(timeout=2)
    runner.close(cleanup=cleanup)

    assert cleanup_finished.wait(timeout=2)
    assert len(set(thread_ids)) == 1


def test_service_exposes_operational_session_and_timeline() -> None:
    service, _, kernel = make_service()
    now = datetime.now(timezone.utc)
    session = OperationalSession(
        session_id="session-gui",
        user_id="Ssamir",
        title="Sessão GUI",
        status=SessionStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        ended_at=None,
        context={},
    )
    event = OperationalEvent(
        event_id="event-gui",
        session_id=session.session_id,
        sequence=1,
        event_type=TimelineEventType.SESSION_STARTED,
        occurred_at=now,
        message="Sessão iniciada.",
        workflow_id=None,
        action_type=None,
        details={},
    )
    kernel.session.list_sessions.return_value = (session,)
    kernel.session.get_timeline.return_value = (event,)

    sessions = service.list_operational_sessions(
        status=SessionStatus.ACTIVE,
        limit=5,
    )
    events = service.get_operational_timeline(
        session_id=session.session_id,
        limit=10,
        after_sequence=0,
    )

    assert sessions == (session,)
    assert events == (event,)
    kernel.session.list_sessions.assert_called_once_with(
        status=SessionStatus.ACTIVE,
        limit=5,
    )
    kernel.session.get_timeline.assert_called_once_with(
        session_id=session.session_id,
        limit=10,
        after_sequence=0,
    )


def test_service_exposes_and_executes_resumption_plan() -> None:
    service, controller, _ = make_service()
    plan = ResumptionPlan.not_available("session-gui")
    action = Action(type="system.wait", parameters={"seconds": 0.0})
    execution = ExecutionResult.ok(
        "system.wait",
        "Etapa retomada.",
    )
    controller.get_resumption_plan.return_value = plan
    controller.resume_interrupted_workflow.return_value = (
        [action],
        [execution],
    )

    assert service.get_resumption_plan() is plan
    result = service.resume_interrupted_workflow(
        confirmation_token="token-gui"
    )

    assert result.source == "resumption"
    assert result.success is True
    assert result.action_count == 1
    assert result.message == "Etapa retomada."
    controller.resume_interrupted_workflow.assert_called_once_with(
        confirmation_token="token-gui"
    )


def test_serial_runner_executes_callable_on_command_thread() -> None:
    thread_ids: list[int] = []

    def handler(command: str):
        thread_ids.append(threading.get_ident())
        return command

    def special_operation() -> str:
        thread_ids.append(threading.get_ident())
        return "retomado"

    runner = SerialCommandRunner(handler)
    runner.submit("normal").result(timeout=2)
    result = runner.submit_callable(special_operation).result(timeout=2)
    runner.close()

    assert result == "retomado"
    assert len(set(thread_ids)) == 1
