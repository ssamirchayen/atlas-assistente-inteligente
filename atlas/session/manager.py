"""Gerenciamento compatível e persistente da sessão atual do Atlas."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from typing import Any

from atlas.core.config import SESSION_DB, SESSION_FILE, USER_NAME
from atlas.session.continuity import (
    ContinuityContextBuilder,
    ContinuitySnapshot,
)
from atlas.session.models import (
    OperationalEvent,
    OperationalSession,
    SessionStatus,
    TimelineEventType,
)
from atlas.session.resumption import (
    ResumptionPlan,
    WorkflowResumptionPlanner,
)
from atlas.session.storage import SqliteSessionStore


class SessionManager:
    """Mantém o contexto atual e o histórico de sessões operacionais.

    A API histórica baseada em ``load`` e ``save`` continua disponível. O
    arquivo JSON é mantido como espelho de compatibilidade, enquanto o SQLite
    passa a ser a fonte de verdade para identidade, estado e continuidade.
    """

    def __init__(
        self,
        session_file: str | Path | None = None,
        database_path: str | Path | None = None,
        *,
        user_id: str = USER_NAME,
        session_title: str = "Sessão do Atlas",
    ) -> None:
        self.session_file = Path(session_file or SESSION_FILE)
        self.database_path = Path(database_path or SESSION_DB)
        self.user_id = user_id.strip() or USER_NAME
        self._lock = RLock()
        self._store = SqliteSessionStore(self.database_path)
        self._continuity_builder = ContinuityContextBuilder()
        self._resumption_planner = WorkflowResumptionPlanner()

        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        legacy_context = self._load_legacy_context()
        current = self._store.get_or_create_current(
            user_id=self.user_id,
            title=self._derive_title(
                legacy_context,
                fallback=session_title,
            ),
            context=legacy_context,
        )
        self._current_session_id = current.session_id
        self._write_legacy_mirror(dict(current.context))

    @property
    def session_id(self) -> str:
        """Identificador estável da sessão operacional atual."""

        return self._current_session_id

    def _default_session(self) -> dict[str, Any]:
        return {
            "project": None,
            "current_task": None,
            "last_file": None,
            "last_command": None,
            "active_window": None,
            "opened_files": [],
            "browser_tabs": [],
            "notes": [],
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

    def load(self) -> dict[str, Any]:
        """Carrega o contexto da fonte persistente e aplica o schema atual."""

        with self._lock:
            current = self._require_current()
            data = dict(current.context)
            defaults = self._default_session()

            for key, value in defaults.items():
                data.setdefault(key, value)

            return data

    def save(self, data: dict[str, Any]) -> None:
        """Persiste o contexto no SQLite e atualiza o espelho JSON."""

        with self._lock:
            updated = dict(data)
            updated["last_update"] = datetime.now(
                timezone.utc
            ).isoformat()
            current = self._require_current()
            self._store.save_context(
                self._current_session_id,
                updated,
                title=self._derive_title(
                    updated,
                    fallback=current.title,
                ),
            )
            self._write_legacy_mirror(updated)

    def clear(self) -> None:
        self.save(self._default_session())

    def update(self, **values: Any) -> None:
        session = self.load()
        session.update(values)
        self.save(session)

    def save_last_command(self, command: str) -> None:
        self.update(last_command=command)

    def save_last_file(self, filename: str) -> None:
        session = self.load()
        opened_files = list(session.get("opened_files", []))

        if filename not in opened_files:
            opened_files.append(filename)

        session["opened_files"] = opened_files
        session["last_file"] = filename
        self.save(session)

    def save_project(self, project: str) -> None:
        self.update(project=project)

    def save_current_task(self, task: str) -> None:
        self.update(current_task=task)

    def save_active_window(self, window_title: str) -> None:
        self.update(active_window=window_title)

    def add_opened_file(self, filename: str) -> None:
        self.save_last_file(filename)

    def remove_opened_file(self, filename: str) -> None:
        session = self.load()
        opened_files = list(session.get("opened_files", []))

        if filename in opened_files:
            opened_files.remove(filename)

        session["opened_files"] = opened_files
        self.save(session)

    def add_browser_tab(self, tab_title: str) -> None:
        session = self.load()
        browser_tabs = list(session.get("browser_tabs", []))

        if tab_title not in browser_tabs:
            browser_tabs.append(tab_title)

        session["browser_tabs"] = browser_tabs
        self.save(session)

    def remove_browser_tab(self, tab_title: str) -> None:
        session = self.load()
        browser_tabs = list(session.get("browser_tabs", []))

        if tab_title in browser_tabs:
            browser_tabs.remove(tab_title)

        session["browser_tabs"] = browser_tabs
        self.save(session)

    def add_note(self, note: str) -> None:
        session = self.load()
        notes = list(session.get("notes", []))

        if note not in notes:
            notes.append(note)

        session["notes"] = notes
        self.save(session)

    def remove_note(self, note: str) -> None:
        session = self.load()
        notes = list(session.get("notes", []))

        if note in notes:
            notes.remove(note)

        session["notes"] = notes
        self.save(session)

    def get_project(self) -> str | None:
        return self.load().get("project")

    def get_current_task(self) -> str | None:
        return self.load().get("current_task")

    def get_last_file(self) -> str | None:
        return self.load().get("last_file")

    def get_last_command(self) -> str | None:
        return self.load().get("last_command")

    def get_context(self) -> dict[str, Any]:
        return self.load()

    def get_operational_session(self) -> OperationalSession:
        """Retorna o snapshot completo da sessão atual."""

        with self._lock:
            return self._require_current()

    def list_sessions(
        self,
        *,
        status: SessionStatus | None = None,
        limit: int = 20,
    ) -> tuple[OperationalSession, ...]:
        return self._store.list_sessions(
            user_id=self.user_id,
            status=status,
            limit=limit,
        )

    def record_event(
        self,
        event_type: TimelineEventType,
        message: str,
        *,
        workflow_id: str | None = None,
        action_type: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> OperationalEvent:
        """Registra uma ocorrência vinculada à sessão atual."""

        with self._lock:
            return self._store.record_event(
                self._current_session_id,
                event_type,
                message,
                workflow_id=workflow_id,
                action_type=action_type,
                details=details,
            )

    def get_timeline(
        self,
        *,
        session_id: str | None = None,
        limit: int = 100,
        after_sequence: int | None = None,
        newest_first: bool = False,
    ) -> tuple[OperationalEvent, ...]:
        """Consulta a linha do tempo de uma sessão pertencente ao usuário."""

        with self._lock:
            target_id = session_id or self._current_session_id
            target = self._store.get(target_id)

            if target is None:
                raise ValueError("A sessão solicitada não foi encontrada.")

            if target.user_id != self.user_id:
                raise ValueError("A sessão pertence a outro usuário.")

            return self._store.list_events(
                target_id,
                limit=limit,
                after_sequence=after_sequence,
                newest_first=newest_first,
            )

    def get_continuity_context(
        self,
        *,
        session_id: str | None = None,
        event_limit: int = 100,
    ) -> ContinuitySnapshot:
        """Monta o contexto compacto de uma sessão pertencente ao usuário."""

        with self._lock:
            target_id = session_id or self._current_session_id
            target = self._store.get(target_id)

            if target is None:
                raise ValueError("A sessão solicitada não foi encontrada.")

            if target.user_id != self.user_id:
                raise ValueError("A sessão pertence a outro usuário.")

            events = self._store.list_events(
                target_id,
                limit=event_limit,
            )
            return self._continuity_builder.build(target, events)

    def get_resumption_plan(
        self,
        *,
        session_id: str | None = None,
        event_limit: int = 1000,
    ) -> ResumptionPlan:
        """Reconstrói uma retomada segura sem executar nenhuma ação."""

        with self._lock:
            target_id = session_id or self._current_session_id
            target = self._store.get(target_id)

            if target is None:
                raise ValueError("A sessão solicitada não foi encontrada.")

            if target.user_id != self.user_id:
                raise ValueError("A sessão pertence a outro usuário.")

            events = self._store.list_events(
                target_id,
                limit=event_limit,
            )
            return self._resumption_planner.build(target, events)

    def start_new_session(
        self,
        *,
        title: str = "Sessão do Atlas",
        context: dict[str, Any] | None = None,
    ) -> OperationalSession:
        """Pausa a sessão atual e inicia um novo espaço de trabalho."""

        with self._lock:
            current = self._require_current()

            if current.status is SessionStatus.ACTIVE:
                self._store.transition(
                    current.session_id,
                    SessionStatus.PAUSED,
                )

            new_context = dict(context or self._default_session())
            created = self._store.create_session(
                user_id=self.user_id,
                title=title,
                context=new_context,
            )
            self._current_session_id = created.session_id
            self._write_legacy_mirror(new_context)
            return created

    def resume_session(
        self,
        session_id: str,
    ) -> OperationalSession:
        """Retoma uma sessão pausada e a torna a sessão atual."""

        with self._lock:
            target = self._store.get(session_id)

            if target is None:
                raise ValueError("A sessão solicitada não foi encontrada.")

            if target.user_id != self.user_id:
                raise ValueError("A sessão pertence a outro usuário.")

            if not target.is_resumable:
                raise ValueError("Uma sessão finalizada não pode ser retomada.")

            current = self._require_current()

            if (
                current.session_id != target.session_id
                and current.status is SessionStatus.ACTIVE
            ):
                self._store.transition(
                    current.session_id,
                    SessionStatus.PAUSED,
                )

            if target.status is SessionStatus.PAUSED:
                target = self._store.transition(
                    target.session_id,
                    SessionStatus.ACTIVE,
                )

            self._current_session_id = target.session_id
            self._write_legacy_mirror(dict(target.context))
            return target

    def pause_current_session(self) -> OperationalSession:
        return self._transition_current(SessionStatus.PAUSED)

    def complete_current_session(self) -> OperationalSession:
        return self._transition_current(SessionStatus.COMPLETED)

    def fail_current_session(self) -> OperationalSession:
        return self._transition_current(SessionStatus.FAILED)

    def cancel_current_session(self) -> OperationalSession:
        return self._transition_current(SessionStatus.CANCELLED)

    def get_summary(self) -> str:
        session = self.load()
        operational = self.get_operational_session()
        opened_files = session.get("opened_files", [])
        browser_tabs = session.get("browser_tabs", [])
        notes = session.get("notes", [])
        files_text = ", ".join(opened_files) if opened_files else "Nenhum"
        tabs_text = ", ".join(browser_tabs) if browser_tabs else "Nenhuma"
        notes_text = (
            "\n".join(f"- {note}" for note in notes)
            if notes
            else "Nenhuma"
        )

        return (
            f"Sessão: {operational.session_id}\n"
            f"Estado: {operational.status.value}\n"
            f"Projeto: {session.get('project') or 'Desconhecido'}\n"
            f"Tarefa atual: {session.get('current_task') or 'Nenhuma'}\n"
            f"Último arquivo: {session.get('last_file') or 'Nenhum'}\n"
            f"Último comando: {session.get('last_command') or 'Nenhum'}\n"
            f"Janela ativa: "
            f"{session.get('active_window') or 'Desconhecida'}\n"
            f"Arquivos abertos: {files_text}\n"
            f"Abas do navegador: {tabs_text}\n"
            f"Anotações:\n{notes_text}\n"
            f"Última atualização: "
            f"{session.get('last_update') or 'Desconhecida'}"
        )

    def build_prompt_context(self, *, max_chars: int = 6000) -> str:
        """Retorna somente o contexto operacional relevante ao modelo."""

        return self.get_continuity_context().to_prompt(
            max_chars=max_chars
        )

    def close(self) -> None:
        self._store.close()

    def _transition_current(
        self,
        status: SessionStatus,
    ) -> OperationalSession:
        with self._lock:
            return self._store.transition(
                self._current_session_id,
                status,
            )

    def _require_current(self) -> OperationalSession:
        current = self._store.get(self._current_session_id)

        if current is None:
            raise RuntimeError("A sessão operacional atual foi perdida.")

        return current

    def _load_legacy_context(self) -> dict[str, Any]:
        try:
            with self.session_file.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                return self._default_session()

            defaults = self._default_session()

            for key, value in defaults.items():
                data.setdefault(key, value)

            return data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return self._default_session()

    def _write_legacy_mirror(self, data: dict[str, Any]) -> None:
        temporary = self.session_file.with_suffix(
            f"{self.session_file.suffix}.tmp"
        )

        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(
                    data,
                    file,
                    indent=4,
                    ensure_ascii=False,
                    default=str,
                )

            temporary.replace(self.session_file)
        except OSError:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _derive_title(
        context: dict[str, Any],
        *,
        fallback: str,
    ) -> str:
        project = str(context.get("project") or "").strip()
        current_task = str(context.get("current_task") or "").strip()

        if project and current_task:
            return f"{project} — {current_task}"[:200]

        if project:
            return project[:200]

        if current_task:
            return current_task[:200]

        return fallback.strip()[:200] or "Sessão do Atlas"
