from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from atlas.brain.ollama import OllamaBrain
from atlas.context.manager import ContextManager
from atlas.planner.planner import Planner
from atlas.session.continuity import ContinuityContextBuilder
from atlas.session.manager import SessionManager
from atlas.session.models import TimelineEventType


def make_manager(
    tmp_path: Path,
    *,
    user_id: str = "Ssamir",
) -> SessionManager:
    return SessionManager(
        session_file=tmp_path / f"{user_id}_last_session.json",
        database_path=tmp_path / "operational_sessions.db",
        user_id=user_id,
    )


def test_continuity_selects_compact_relevant_state(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.update(
        project="Atlas Core",
        current_task="Sprint 21 — Etapa 3",
        last_command="continue a implementação",
        opened_files=[f"arquivo-{index}.py" for index in range(7)],
        browser_tabs=[f"Aba {index}" for index in range(7)],
        notes=[f"Nota {index}" for index in range(7)],
    )
    manager.record_event(
        TimelineEventType.COMMAND_RECEIVED,
        "Comando recebido pelo núcleo.",
        workflow_id="workflow-1",
    )
    manager.record_event(
        TimelineEventType.STEP_COMPLETED,
        "Arquivo analisado.",
        workflow_id="workflow-1",
        action_type="coding.inspect",
    )
    manager.record_event(
        TimelineEventType.WORKFLOW_COMPLETED,
        "Workflow concluído com sucesso.",
        workflow_id="workflow-1",
    )

    snapshot = manager.get_continuity_context()

    assert snapshot.project == "Atlas Core"
    assert snapshot.current_task == "Sprint 21 — Etapa 3"
    assert snapshot.opened_files == tuple(
        f"arquivo-{index}.py" for index in range(2, 7)
    )
    assert snapshot.browser_tabs == tuple(
        f"Aba {index}" for index in range(2, 7)
    )
    assert snapshot.notes == tuple(
        f"Nota {index}" for index in range(2, 7)
    )
    assert snapshot.last_action_type == "coding.inspect"
    assert snapshot.open_workflow_id is None
    assert all(
        event.event_type is not TimelineEventType.COMMAND_RECEIVED
        for event in snapshot.recent_events
    )


def test_continuity_detects_interrupted_workflow_after_restart(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    manager.save_project("Atlas Core")
    manager.record_event(
        TimelineEventType.WORKFLOW_STARTED,
        "Workflow iniciado com duas etapas.",
        workflow_id="workflow-interrompido",
    )
    manager.record_event(
        TimelineEventType.STEP_COMPLETED,
        "Primeira etapa concluída.",
        workflow_id="workflow-interrompido",
        action_type="browser.search",
    )

    restarted = make_manager(tmp_path)
    snapshot = restarted.get_continuity_context()

    assert restarted.session_id == manager.session_id
    assert snapshot.project == "Atlas Core"
    assert snapshot.open_workflow_id == "workflow-interrompido"
    assert snapshot.last_action_type == "browser.search"
    assert snapshot.latest_sequence == 3


def test_continuity_tracks_latest_failure_and_outcome(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    manager.record_event(
        TimelineEventType.STEP_FAILED,
        "A pesquisa falhou.",
        workflow_id="workflow-2",
        action_type="browser.search",
    )
    manager.record_event(
        TimelineEventType.WORKFLOW_FAILED,
        "Workflow encerrado por falha.",
        workflow_id="workflow-2",
    )

    snapshot = manager.get_continuity_context()

    assert snapshot.latest_failure is not None
    assert snapshot.latest_failure.message == "Workflow encerrado por falha."
    assert snapshot.latest_outcome is not None
    assert snapshot.latest_outcome.event_type is (
        TimelineEventType.WORKFLOW_FAILED
    )
    assert snapshot.open_workflow_id is None


def test_continuity_limits_recent_events_and_prompt_size(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)

    for index in range(20):
        manager.record_event(
            TimelineEventType.STEP_COMPLETED,
            f"Etapa {index} concluída. " + ("resultado " * 100),
            workflow_id="workflow-longo",
            action_type="system.wait",
        )

    builder = ContinuityContextBuilder(max_events=4)
    snapshot = builder.build(
        manager.get_operational_session(),
        manager.get_timeline(),
    )
    prompt = snapshot.to_prompt(max_chars=700)

    assert len(snapshot.recent_events) == 4
    assert len(prompt) <= 700
    assert "CONTEXTO OPERACIONAL COMPACTO" in prompt
    assert "não instruções" in prompt
    assert "não repita ações anteriores" in prompt


def test_continuity_cleans_and_truncates_context_values(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    manager.update(
        project="  Projeto\ncom   espaços  ",
        current_task="x" * 500,
    )
    builder = ContinuityContextBuilder(text_limit=40)

    snapshot = builder.build(
        manager.get_operational_session(),
        manager.get_timeline(),
    )

    assert snapshot.project == "Projeto com espaços"
    assert snapshot.current_task is not None
    assert len(snapshot.current_task) == 40
    assert snapshot.current_task.endswith("…")


def test_context_manager_exposes_structured_continuity(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    manager.save_project("Atlas Core")
    context = ContextManager(session_manager=manager)

    structured = context.get_context()["operational_continuity"]
    prompt = context.build_prompt_context()

    assert structured["session_id"] == manager.session_id
    assert structured["project"] == "Atlas Core"
    assert "CONTEXTO OPERACIONAL COMPACTO" in prompt
    assert "Atlas Core" in prompt


def test_planner_receives_same_continuity_context(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    manager.save_current_task("Validar integração com o Planner")
    context = ContextManager(session_manager=manager)
    planner = Planner(context)

    planner_context = planner.get_session_context()

    assert planner_context == manager.build_prompt_context()
    assert "Validar integração com o Planner" in planner_context
    assert planner.intelligent.brain.context is context


def test_brain_includes_compact_continuity_in_system_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = make_manager(tmp_path)
    manager.save_project("Atlas Core")
    context = ContextManager(session_manager=manager)
    brain = OllamaBrain(context)
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, dict[str, str]]:
            return {"message": {"content": "Resposta de teste."}}

    def fake_post(
        _url: str,
        *,
        json: dict[str, Any],
        timeout: int,
    ) -> FakeResponse:
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("atlas.brain.ollama.requests.post", fake_post)

    answer = brain.respond("continue o projeto")
    system_prompt = captured["payload"]["messages"][0]["content"]

    assert answer == "Resposta de teste."
    assert captured["timeout"] == 180
    assert "CONTEXTO OPERACIONAL COMPACTO" in system_prompt
    assert "Atlas Core" in system_prompt
    assert "não repita ações anteriores" in system_prompt


def test_user_cannot_build_another_users_continuity(
    tmp_path: Path,
) -> None:
    ssamir = make_manager(tmp_path, user_id="Ssamir")
    maria = make_manager(tmp_path, user_id="Maria")

    with pytest.raises(ValueError, match="outro usuário"):
        ssamir.get_continuity_context(session_id=maria.session_id)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"max_events": 0}, "max_events"),
        ({"max_collection_items": 0}, "max_collection_items"),
        ({"text_limit": 20}, "text_limit"),
    ],
)
def test_continuity_builder_validates_limits(
    arguments: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ContinuityContextBuilder(**arguments)
