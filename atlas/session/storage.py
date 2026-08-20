"""Persistência SQLite das sessões operacionais do Atlas."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Any
from uuid import uuid4

from atlas.session.models import (
    OperationalEvent,
    OperationalSession,
    SessionStatus,
    TimelineEventType,
)


class SessionStorageError(RuntimeError):
    """Indica indisponibilidade ou inconsistência no banco de sessões."""


_ALLOWED_TRANSITIONS: dict[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.ACTIVE: frozenset(
        {
            SessionStatus.PAUSED,
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        }
    ),
    SessionStatus.PAUSED: frozenset(
        {
            SessionStatus.ACTIVE,
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        }
    ),
    SessionStatus.COMPLETED: frozenset(),
    SessionStatus.FAILED: frozenset(),
    SessionStatus.CANCELLED: frozenset(),
}

_TRANSITION_EVENT_TYPES: dict[SessionStatus, TimelineEventType] = {
    SessionStatus.ACTIVE: TimelineEventType.SESSION_RESUMED,
    SessionStatus.PAUSED: TimelineEventType.SESSION_PAUSED,
    SessionStatus.COMPLETED: TimelineEventType.SESSION_COMPLETED,
    SessionStatus.FAILED: TimelineEventType.SESSION_FAILED,
    SessionStatus.CANCELLED: TimelineEventType.SESSION_CANCELLED,
}


class SqliteSessionStore:
    """Repositório transacional e thread-safe de sessões operacionais."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._initialization_lock = Lock()
        self._initialized = False

    @property
    def database_path(self) -> Path:
        return self._database_path

    def get_or_create_current(
        self,
        *,
        user_id: str,
        title: str,
        context: Mapping[str, Any],
    ) -> OperationalSession:
        """Retoma a última sessão aberta ou cria uma sessão nova."""

        clean_user_id = self._require_text(user_id, "usuário")
        clean_title = self._clean_title(title)
        now = datetime.now(timezone.utc)

        try:
            with self._write_connection() as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM operational_sessions
                    WHERE user_id = ? AND status IN (?, ?)
                    ORDER BY
                        CASE status WHEN 'active' THEN 0 ELSE 1 END,
                        updated_at DESC,
                        rowid DESC
                    LIMIT 1
                    """,
                    (
                        clean_user_id,
                        SessionStatus.ACTIVE.value,
                        SessionStatus.PAUSED.value,
                    ),
                ).fetchone()

                if row is None:
                    return self._insert_session(
                        connection,
                        user_id=clean_user_id,
                        title=clean_title,
                        context=context,
                        now=now,
                    )

                if row["status"] == SessionStatus.PAUSED.value:
                    connection.execute(
                        """
                        UPDATE operational_sessions
                        SET status = ?, updated_at = ?, ended_at = NULL
                        WHERE session_id = ?
                        """,
                        (
                            SessionStatus.ACTIVE.value,
                            now.isoformat(),
                            row["session_id"],
                        ),
                    )
                    self._insert_event(
                        connection,
                        session_id=row["session_id"],
                        event_type=TimelineEventType.SESSION_RESUMED,
                        occurred_at=now,
                        message="Sessão operacional retomada.",
                    )
                    row = connection.execute(
                        """
                        SELECT * FROM operational_sessions
                        WHERE session_id = ?
                        """,
                        (row["session_id"],),
                    ).fetchone()

                return self._row_to_session(row)
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível abrir a sessão operacional."
            ) from error

    def create_session(
        self,
        *,
        user_id: str,
        title: str,
        context: Mapping[str, Any],
    ) -> OperationalSession:
        """Cria uma sessão independente sem alterar sessões anteriores."""

        clean_user_id = self._require_text(user_id, "usuário")
        clean_title = self._clean_title(title)
        now = datetime.now(timezone.utc)

        try:
            with self._write_connection() as connection:
                return self._insert_session(
                    connection,
                    user_id=clean_user_id,
                    title=clean_title,
                    context=context,
                    now=now,
                )
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível criar a sessão operacional."
            ) from error

    def get(self, session_id: str) -> OperationalSession | None:
        clean_session_id = self._require_text(session_id, "sessão")

        try:
            self._ensure_initialized()

            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM operational_sessions
                    WHERE session_id = ?
                    """,
                    (clean_session_id,),
                ).fetchone()
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível consultar a sessão operacional."
            ) from error

        return self._row_to_session(row) if row is not None else None

    def save_context(
        self,
        session_id: str,
        context: Mapping[str, Any],
        *,
        title: str | None = None,
    ) -> OperationalSession:
        """Atualiza contexto e horário sem perder a identidade da sessão."""

        clean_session_id = self._require_text(session_id, "sessão")
        context_json = self._serialize_context(context)
        now = datetime.now(timezone.utc).isoformat()

        try:
            with self._write_connection() as connection:
                if title is None:
                    cursor = connection.execute(
                        """
                        UPDATE operational_sessions
                        SET context_json = ?, updated_at = ?
                        WHERE session_id = ?
                        """,
                        (context_json, now, clean_session_id),
                    )
                else:
                    cursor = connection.execute(
                        """
                        UPDATE operational_sessions
                        SET context_json = ?, title = ?, updated_at = ?
                        WHERE session_id = ?
                        """,
                        (
                            context_json,
                            self._clean_title(title),
                            now,
                            clean_session_id,
                        ),
                    )

                if cursor.rowcount != 1:
                    raise SessionStorageError(
                        "A sessão operacional não foi encontrada."
                    )

                row = connection.execute(
                    """
                    SELECT * FROM operational_sessions
                    WHERE session_id = ?
                    """,
                    (clean_session_id,),
                ).fetchone()
        except SessionStorageError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível atualizar a sessão operacional."
            ) from error

        return self._row_to_session(row)

    def transition(
        self,
        session_id: str,
        status: SessionStatus,
    ) -> OperationalSession:
        """Aplica uma transição de estado validada e auditável."""

        clean_session_id = self._require_text(session_id, "sessão")
        now = datetime.now(timezone.utc)

        try:
            with self._write_connection() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM operational_sessions
                    WHERE session_id = ?
                    """,
                    (clean_session_id,),
                ).fetchone()

                if row is None:
                    raise SessionStorageError(
                        "A sessão operacional não foi encontrada."
                    )

                current = SessionStatus(row["status"])

                if status == current:
                    return self._row_to_session(row)

                if status not in _ALLOWED_TRANSITIONS[current]:
                    raise ValueError(
                        "Transição de sessão inválida: "
                        f"{current.value} -> {status.value}."
                    )

                ended_at = now.isoformat() if status.is_terminal else None
                connection.execute(
                    """
                    UPDATE operational_sessions
                    SET status = ?, updated_at = ?, ended_at = ?
                    WHERE session_id = ?
                    """,
                    (
                        status.value,
                        now.isoformat(),
                        ended_at,
                        clean_session_id,
                    ),
                )
                self._insert_event(
                    connection,
                    session_id=clean_session_id,
                    event_type=_TRANSITION_EVENT_TYPES[status],
                    occurred_at=now,
                    message=(
                        "Estado da sessão alterado para "
                        f"{status.value}."
                    ),
                )
                updated = connection.execute(
                    """
                    SELECT * FROM operational_sessions
                    WHERE session_id = ?
                    """,
                    (clean_session_id,),
                ).fetchone()
        except (SessionStorageError, ValueError):
            raise
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível alterar o estado da sessão."
            ) from error

        return self._row_to_session(updated)

    def record_event(
        self,
        session_id: str,
        event_type: TimelineEventType,
        message: str,
        *,
        workflow_id: str | None = None,
        action_type: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> OperationalEvent:
        """Acrescenta um evento ordenado à linha do tempo da sessão."""

        clean_session_id = self._require_text(session_id, "sessão")
        now = datetime.now(timezone.utc)

        try:
            with self._write_connection() as connection:
                exists = connection.execute(
                    """
                    SELECT 1 FROM operational_sessions
                    WHERE session_id = ?
                    """,
                    (clean_session_id,),
                ).fetchone()

                if exists is None:
                    raise SessionStorageError(
                        "A sessão operacional não foi encontrada."
                    )

                event = self._insert_event(
                    connection,
                    session_id=clean_session_id,
                    event_type=event_type,
                    occurred_at=now,
                    message=message,
                    workflow_id=workflow_id,
                    action_type=action_type,
                    details=details,
                )
                connection.execute(
                    """
                    UPDATE operational_sessions
                    SET updated_at = ?
                    WHERE session_id = ?
                    """,
                    (now.isoformat(), clean_session_id),
                )
        except SessionStorageError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível registrar o evento operacional."
            ) from error

        return event

    def list_events(
        self,
        session_id: str,
        *,
        limit: int = 100,
        after_sequence: int | None = None,
        newest_first: bool = False,
    ) -> tuple[OperationalEvent, ...]:
        """Lista os eventos mais recentes sem perder a ordem cronológica."""

        clean_session_id = self._require_text(session_id, "sessão")

        if limit < 1 or limit > 1000:
            raise ValueError("O limite deve estar entre 1 e 1000.")

        if after_sequence is not None and after_sequence < 0:
            raise ValueError("A sequência inicial não pode ser negativa.")

        conditions = ["session_id = ?"]
        parameters: list[object] = [clean_session_id]

        if after_sequence is not None:
            conditions.append("sequence > ?")
            parameters.append(after_sequence)

        parameters.append(limit)

        try:
            self._ensure_initialized()

            with self._connect() as connection:
                exists = connection.execute(
                    """
                    SELECT 1 FROM operational_sessions
                    WHERE session_id = ?
                    """,
                    (clean_session_id,),
                ).fetchone()

                if exists is None:
                    raise SessionStorageError(
                        "A sessão operacional não foi encontrada."
                    )

                rows = connection.execute(
                    f"""
                    SELECT * FROM operational_events
                    WHERE {' AND '.join(conditions)}
                    ORDER BY sequence DESC
                    LIMIT ?
                    """,  # noqa: S608 - condições montadas internamente.
                    parameters,
                ).fetchall()
        except SessionStorageError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível consultar a linha do tempo."
            ) from error

        events = [self._row_to_event(row) for row in rows]

        if not newest_first:
            events.reverse()

        return tuple(events)

    def list_sessions(
        self,
        *,
        user_id: str | None = None,
        status: SessionStatus | None = None,
        limit: int = 20,
    ) -> tuple[OperationalSession, ...]:
        if limit < 1 or limit > 500:
            raise ValueError("O limite deve estar entre 1 e 500.")

        conditions: list[str] = []
        parameters: list[object] = []

        if user_id is not None:
            conditions.append("user_id = ?")
            parameters.append(self._require_text(user_id, "usuário"))

        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit)

        try:
            self._ensure_initialized()

            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT * FROM operational_sessions
                    {where}
                    ORDER BY updated_at DESC, rowid DESC
                    LIMIT ?
                    """,  # noqa: S608 - cláusula montada apenas internamente.
                    parameters,
                ).fetchall()
        except (OSError, sqlite3.Error) as error:
            raise SessionStorageError(
                "Não foi possível listar as sessões operacionais."
            ) from error

        return tuple(self._row_to_session(row) for row in rows)

    def close(self) -> None:
        """Mantido para composição uniforme; conexões são curtas."""

    def _write_connection(self) -> sqlite3.Connection:
        self._ensure_initialized()
        connection = self._connect()
        connection.execute("BEGIN IMMEDIATE")
        return connection

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        with self._initialization_lock:
            if self._initialized:
                return

            self._database_path.parent.mkdir(parents=True, exist_ok=True)

            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS operational_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        ended_at TEXT,
                        context_json TEXT NOT NULL,
                        CHECK (
                            status IN (
                                'active',
                                'paused',
                                'completed',
                                'failed',
                                'cancelled'
                            )
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_sessions_user_updated
                    ON operational_sessions (user_id, updated_at DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_sessions_status_updated
                    ON operational_sessions (status, updated_at DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active
                    ON operational_sessions (user_id)
                    WHERE status = 'active'
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS operational_events (
                        event_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        workflow_id TEXT,
                        action_type TEXT,
                        message TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        FOREIGN KEY (session_id)
                            REFERENCES operational_sessions (session_id)
                            ON DELETE CASCADE,
                        UNIQUE (session_id, sequence)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_events_session_sequence
                    ON operational_events (session_id, sequence DESC)
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_events_workflow
                    ON operational_events (workflow_id, occurred_at DESC)
                    WHERE workflow_id IS NOT NULL
                    """
                )

            self._initialized = True

    def _insert_session(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: str,
        title: str,
        context: Mapping[str, Any],
        now: datetime,
    ) -> OperationalSession:
        session_id = str(uuid4())
        serialized = self._serialize_context(context)
        timestamp = now.isoformat()
        connection.execute(
            """
            INSERT INTO operational_sessions (
                session_id,
                user_id,
                title,
                status,
                created_at,
                updated_at,
                ended_at,
                context_json
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                session_id,
                user_id,
                title,
                SessionStatus.ACTIVE.value,
                timestamp,
                timestamp,
                serialized,
            ),
        )
        self._insert_event(
            connection,
            session_id=session_id,
            event_type=TimelineEventType.SESSION_STARTED,
            occurred_at=now,
            message="Sessão operacional iniciada.",
        )
        return OperationalSession(
            session_id=session_id,
            user_id=user_id,
            title=title,
            status=SessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            ended_at=None,
            context=dict(context),
        )

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        event_type: TimelineEventType,
        occurred_at: datetime,
        message: str,
        workflow_id: str | None = None,
        action_type: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> OperationalEvent:
        next_row = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
            FROM operational_events
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        sequence = int(next_row["next_sequence"])
        event_id = str(uuid4())
        clean_message = self._clean_message(message)
        clean_workflow_id = self._optional_text(workflow_id, 200)
        clean_action_type = self._optional_text(action_type, 200)
        event_details = dict(details or {})
        connection.execute(
            """
            INSERT INTO operational_events (
                event_id,
                session_id,
                sequence,
                event_type,
                occurred_at,
                workflow_id,
                action_type,
                message,
                details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                session_id,
                sequence,
                event_type.value,
                occurred_at.isoformat(),
                clean_workflow_id,
                clean_action_type,
                clean_message,
                self._serialize_details(event_details),
            ),
        )
        return OperationalEvent(
            event_id=event_id,
            session_id=session_id,
            sequence=sequence,
            event_type=event_type,
            occurred_at=occurred_at,
            message=clean_message,
            workflow_id=clean_workflow_id,
            action_type=clean_action_type,
            details=event_details,
        )

    @staticmethod
    def _serialize_context(context: Mapping[str, Any]) -> str:
        try:
            return json.dumps(
                dict(context),
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "O contexto da sessão não pode ser serializado."
            ) from error

    @staticmethod
    def _serialize_details(details: Mapping[str, Any]) -> str:
        try:
            return json.dumps(
                dict(details),
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Os detalhes do evento não podem ser serializados."
            ) from error

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> OperationalSession:
        context = json.loads(row["context_json"])

        if not isinstance(context, dict):
            raise SessionStorageError(
                "O contexto persistido da sessão é inválido."
            )

        return OperationalSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            title=row["title"],
            status=SessionStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            ended_at=(
                datetime.fromisoformat(row["ended_at"])
                if row["ended_at"] is not None
                else None
            ),
            context=context,
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> OperationalEvent:
        details = json.loads(row["details_json"])

        if not isinstance(details, dict):
            raise SessionStorageError(
                "Os detalhes persistidos do evento são inválidos."
            )

        try:
            event_type = TimelineEventType(row["event_type"])
        except ValueError as error:
            raise SessionStorageError(
                "O tipo persistido do evento é inválido."
            ) from error

        return OperationalEvent(
            event_id=row["event_id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            event_type=event_type,
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            message=row["message"],
            workflow_id=row["workflow_id"],
            action_type=row["action_type"],
            details=details,
        )

    @staticmethod
    def _require_text(value: str, label: str) -> str:
        clean_value = value.strip()

        if not clean_value:
            raise ValueError(f"O identificador de {label} é obrigatório.")

        return clean_value[:200]

    @staticmethod
    def _clean_title(title: str) -> str:
        clean_title = title.strip()
        return clean_title[:200] or "Sessão do Atlas"

    @staticmethod
    def _clean_message(message: str) -> str:
        clean_message = message.strip()

        if not clean_message:
            raise ValueError("A mensagem do evento é obrigatória.")

        return clean_message[:4000]

    @staticmethod
    def _optional_text(value: str | None, limit: int) -> str | None:
        if value is None:
            return None

        clean_value = value.strip()
        return clean_value[:limit] or None
