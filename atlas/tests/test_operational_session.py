from __future__ import annotations

from datetime import timezone
import json
from pathlib import Path

import pytest

from atlas.session.manager import SessionManager
from atlas.session.models import SessionStatus
from atlas.session.storage import SqliteSessionStore


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


def test_first_start_creates_identified_active_session(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)

    session = manager.get_operational_session()

    assert session.session_id == manager.session_id
    assert session.user_id == "Ssamir"
    assert session.status is SessionStatus.ACTIVE
    assert session.is_resumable is True
    assert session.created_at.tzinfo == timezone.utc
    assert session.updated_at.tzinfo == timezone.utc
    assert session.ended_at is None


def test_context_survives_manager_restart(tmp_path: Path) -> None:
    first = make_manager(tmp_path)
    first.save_project("Atlas Core")
    first.save_current_task("Preparar continuidade")
    first.save_last_command("continue a implementação")
    session_id = first.session_id

    restarted = make_manager(tmp_path)

    assert restarted.session_id == session_id
    assert restarted.get_project() == "Atlas Core"
    assert restarted.get_current_task() == "Preparar continuidade"
    assert restarted.get_last_command() == "continue a implementação"
    assert restarted.get_operational_session().title == (
        "Atlas Core — Preparar continuidade"
    )


def test_existing_json_is_migrated_on_first_start(tmp_path: Path) -> None:
    session_file = tmp_path / "last_session.json"
    session_file.write_text(
        json.dumps(
            {
                "project": "Projeto legado",
                "last_command": "retomar o projeto",
            }
        ),
        encoding="utf-8",
    )

    manager = SessionManager(
        session_file=session_file,
        database_path=tmp_path / "operational_sessions.db",
        user_id="Ssamir",
    )

    assert manager.get_project() == "Projeto legado"
    assert manager.get_last_command() == "retomar o projeto"
    assert manager.get_operational_session().title == "Projeto legado"


def test_json_remains_a_compatibility_mirror(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    manager.save_last_file("atlas/session/storage.py")

    mirrored = json.loads(manager.session_file.read_text(encoding="utf-8"))
    assert mirrored["last_file"] == "atlas/session/storage.py"
    assert mirrored["opened_files"] == ["atlas/session/storage.py"]


def test_new_session_pauses_current_and_can_resume_it(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    manager.save_project("Primeiro projeto")
    first_id = manager.session_id

    second = manager.start_new_session(title="Segundo projeto")

    sessions = {item.session_id: item for item in manager.list_sessions()}
    assert second.session_id != first_id
    assert sessions[first_id].status is SessionStatus.PAUSED
    assert sessions[second.session_id].status is SessionStatus.ACTIVE

    resumed = manager.resume_session(first_id)
    sessions = {item.session_id: item for item in manager.list_sessions()}

    assert resumed.status is SessionStatus.ACTIVE
    assert manager.get_project() == "Primeiro projeto"
    assert sessions[second.session_id].status is SessionStatus.PAUSED


@pytest.mark.parametrize(
    ("method_name", "expected_status"),
    [
        ("complete_current_session", SessionStatus.COMPLETED),
        ("fail_current_session", SessionStatus.FAILED),
        ("cancel_current_session", SessionStatus.CANCELLED),
    ],
)
def test_terminal_transitions_record_end_time(
    tmp_path: Path,
    method_name: str,
    expected_status: SessionStatus,
) -> None:
    manager = make_manager(tmp_path)

    session = getattr(manager, method_name)()

    assert session.status is expected_status
    assert session.ended_at is not None
    assert session.ended_at.tzinfo == timezone.utc
    assert session.is_resumable is False


def test_terminal_session_cannot_be_resumed(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)
    finished = manager.complete_current_session()

    with pytest.raises(ValueError, match="finalizada"):
        manager.resume_session(finished.session_id)


def test_store_rejects_invalid_terminal_transition(
    tmp_path: Path,
) -> None:
    manager = make_manager(tmp_path)
    finished = manager.complete_current_session()
    store = SqliteSessionStore(manager.database_path)

    with pytest.raises(ValueError, match="Transição de sessão inválida"):
        store.transition(finished.session_id, SessionStatus.ACTIVE)


def test_sessions_are_isolated_by_user(tmp_path: Path) -> None:
    ssamir = make_manager(tmp_path, user_id="Ssamir")
    maria = make_manager(tmp_path, user_id="Maria")

    assert ssamir.session_id != maria.session_id
    assert [item.user_id for item in ssamir.list_sessions()] == ["Ssamir"]
    assert [item.user_id for item in maria.list_sessions()] == ["Maria"]


def test_session_snapshot_is_serializable(tmp_path: Path) -> None:
    snapshot = make_manager(tmp_path).get_operational_session().as_dict()

    assert snapshot["status"] == "active"
    assert isinstance(snapshot["created_at"], str)
    assert snapshot["ended_at"] is None
    assert isinstance(snapshot["context"], dict)


def test_list_limit_is_validated(tmp_path: Path) -> None:
    manager = make_manager(tmp_path)

    with pytest.raises(ValueError, match="entre 1 e 500"):
        manager.list_sessions(limit=0)
