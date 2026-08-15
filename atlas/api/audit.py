"""Auditoria persistente e segura da API local do Atlas."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Literal, Protocol
from uuid import uuid4

from atlas.core.config import (
    API_AUDIT_DB,
    API_AUDIT_MAX_EVENTS,
    API_AUDIT_RETENTION_DAYS,
)

AuditOutcome = Literal[
    "accepted",
    "succeeded",
    "rejected",
    "failed",
    "timed_out",
    "cancel_requested",
    "cancelled",
]

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "command",
        "password",
        "reason",
        "secret",
        "token",
        "x_api_key",
    }
)
_MAX_SAFE_TEXT_LENGTH = 500


class AuditStorageError(RuntimeError):
    """Indica indisponibilidade do armazenamento de auditoria."""


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Evento imutável retornado pela trilha de auditoria."""

    event_id: str
    event_type: str
    occurred_at: datetime
    principal_id: str | None
    workflow_id: str | None
    outcome: AuditOutcome
    status_code: int
    duration_ms: float | None
    details: dict[str, object]


class AuditTrail(Protocol):
    """Contrato usado pela aplicação para registrar e consultar eventos."""

    def record(
        self,
        event_type: str,
        *,
        outcome: AuditOutcome,
        status_code: int,
        principal_id: str | None = None,
        workflow_id: str | None = None,
        duration_ms: float | None = None,
        details: Mapping[str, object] | None = None,
    ) -> AuditEvent: ...

    def list_events(
        self,
        *,
        limit: int,
        event_type: str | None = None,
        workflow_id: str | None = None,
    ) -> tuple[AuditEvent, ...]: ...

    def close(self) -> None: ...


def sensitive_fingerprint(label: str, value: str) -> dict[str, object]:
    """Representa conteúdo privado sem persistir o valor original."""

    encoded = value.encode("utf-8")
    return {
        f"{label}_sha256": sha256(encoded).hexdigest(),
        f"{label}_length": len(value),
    }


def _redacted_value(value: object) -> dict[str, object]:
    text = "" if value is None else str(value)
    return {
        "redacted": True,
        "sha256": sha256(text.encode("utf-8")).hexdigest(),
        "length": len(text),
    }


def _safe_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return value[:_MAX_SAFE_TEXT_LENGTH]

    if isinstance(value, Mapping):
        return _sanitize_details(value)

    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:50]]

    return str(value)[:_MAX_SAFE_TEXT_LENGTH]


def _sanitize_details(
    details: Mapping[str, object] | None,
) -> dict[str, object]:
    if not details:
        return {}

    sanitized: dict[str, object] = {}

    for original_key, value in details.items():
        key = str(original_key)[:100]

        if key.strip().lower() in _SENSITIVE_KEYS:
            sanitized[key] = _redacted_value(value)
        else:
            sanitized[key] = _safe_value(value)

    return sanitized


class NullAuditTrail:
    """Implementação sem persistência usada em composições isoladas."""

    def record(
        self,
        event_type: str,
        *,
        outcome: AuditOutcome,
        status_code: int,
        principal_id: str | None = None,
        workflow_id: str | None = None,
        duration_ms: float | None = None,
        details: Mapping[str, object] | None = None,
    ) -> AuditEvent:
        return _new_event(
            event_type,
            outcome=outcome,
            status_code=status_code,
            principal_id=principal_id,
            workflow_id=workflow_id,
            duration_ms=duration_ms,
            details=details,
        )

    def list_events(
        self,
        *,
        limit: int,
        event_type: str | None = None,
        workflow_id: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        del limit, event_type, workflow_id
        return ()

    def close(self) -> None:
        return


class InMemoryAuditTrail:
    """Trilha observável para testes sem tocar nos dados reais do Atlas."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = Lock()

    def record(
        self,
        event_type: str,
        *,
        outcome: AuditOutcome,
        status_code: int,
        principal_id: str | None = None,
        workflow_id: str | None = None,
        duration_ms: float | None = None,
        details: Mapping[str, object] | None = None,
    ) -> AuditEvent:
        event = _new_event(
            event_type,
            outcome=outcome,
            status_code=status_code,
            principal_id=principal_id,
            workflow_id=workflow_id,
            duration_ms=duration_ms,
            details=details,
        )

        with self._lock:
            self._events.append(event)

        return event

    def list_events(
        self,
        *,
        limit: int,
        event_type: str | None = None,
        workflow_id: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        with self._lock:
            filtered = (
                event
                for event in reversed(self._events)
                if (event_type is None or event.event_type == event_type)
                and (
                    workflow_id is None
                    or event.workflow_id == workflow_id
                )
            )
            return tuple(list(filtered)[:limit])

    def close(self) -> None:
        return


class SqliteAuditTrail:
    """Trilha append-only com retenção limitada em banco SQLite local."""

    def __init__(
        self,
        database_path: Path = API_AUDIT_DB,
        *,
        retention_days: int = API_AUDIT_RETENTION_DAYS,
        max_events: int = API_AUDIT_MAX_EVENTS,
    ) -> None:
        if retention_days <= 0:
            raise ValueError("A retenção da auditoria deve ser positiva.")

        if max_events <= 0:
            raise ValueError("O limite de auditoria deve ser positivo.")

        self._database_path = Path(database_path)
        self._retention_days = retention_days
        self._max_events = max_events
        self._lock = Lock()
        self._initialized = False

    def record(
        self,
        event_type: str,
        *,
        outcome: AuditOutcome,
        status_code: int,
        principal_id: str | None = None,
        workflow_id: str | None = None,
        duration_ms: float | None = None,
        details: Mapping[str, object] | None = None,
    ) -> AuditEvent:
        event = _new_event(
            event_type,
            outcome=outcome,
            status_code=status_code,
            principal_id=principal_id,
            workflow_id=workflow_id,
            duration_ms=duration_ms,
            details=details,
        )

        with self._lock:
            try:
                self._ensure_initialized_locked()

                with self._connect() as connection:
                    connection.execute(
                        """
                        INSERT INTO api_audit_events (
                            event_id,
                            event_type,
                            occurred_at,
                            principal_id,
                            workflow_id,
                            outcome,
                            status_code,
                            duration_ms,
                            details_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.event_id,
                            event.event_type,
                            event.occurred_at.isoformat(),
                            event.principal_id,
                            event.workflow_id,
                            event.outcome,
                            event.status_code,
                            event.duration_ms,
                            json.dumps(
                                event.details,
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                        ),
                    )
                    self._apply_retention(connection, event.occurred_at)
            except (OSError, sqlite3.Error) as error:
                raise AuditStorageError(
                    "Não foi possível registrar a auditoria local."
                ) from error

        return event

    def list_events(
        self,
        *,
        limit: int,
        event_type: str | None = None,
        workflow_id: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        if limit <= 0:
            return ()

        clauses: list[str] = []
        parameters: list[object] = []

        if event_type is not None:
            clauses.append("event_type = ?")
            parameters.append(event_type)

        if workflow_id is not None:
            clauses.append("workflow_id = ?")
            parameters.append(workflow_id)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)

        with self._lock:
            try:
                self._ensure_initialized_locked()

                with self._connect() as connection:
                    rows = connection.execute(
                        f"""
                        SELECT
                            event_id,
                            event_type,
                            occurred_at,
                            principal_id,
                            workflow_id,
                            outcome,
                            status_code,
                            duration_ms,
                            details_json
                        FROM api_audit_events
                        {where}
                        ORDER BY occurred_at DESC, rowid DESC
                        LIMIT ?
                        """,
                        parameters,
                    ).fetchall()
            except (OSError, sqlite3.Error) as error:
                raise AuditStorageError(
                    "Não foi possível consultar a auditoria local."
                ) from error

        return tuple(self._row_to_event(row) for row in rows)

    def close(self) -> None:
        return

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_initialized_locked(self) -> None:
        if self._initialized:
            return

        self._database_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    principal_id TEXT,
                    workflow_id TEXT,
                    outcome TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    duration_ms REAL,
                    details_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_audit_occurred_at
                ON api_audit_events (occurred_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_audit_workflow
                ON api_audit_events (workflow_id, occurred_at DESC)
                """
            )

        self._initialized = True

    def _apply_retention(
        self,
        connection: sqlite3.Connection,
        now: datetime,
    ) -> None:
        cutoff = now - timedelta(days=self._retention_days)
        connection.execute(
            "DELETE FROM api_audit_events WHERE occurred_at < ?",
            (cutoff.isoformat(),),
        )
        connection.execute(
            """
            DELETE FROM api_audit_events
            WHERE rowid IN (
                SELECT rowid
                FROM api_audit_events
                ORDER BY occurred_at DESC, rowid DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self._max_events,),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            principal_id=row["principal_id"],
            workflow_id=row["workflow_id"],
            outcome=row["outcome"],
            status_code=row["status_code"],
            duration_ms=row["duration_ms"],
            details=json.loads(row["details_json"]),
        )


def _new_event(
    event_type: str,
    *,
    outcome: AuditOutcome,
    status_code: int,
    principal_id: str | None,
    workflow_id: str | None,
    duration_ms: float | None,
    details: Mapping[str, object] | None,
) -> AuditEvent:
    clean_event_type = event_type.strip()

    if not clean_event_type:
        raise ValueError("O tipo do evento de auditoria é obrigatório.")

    if status_code < 100 or status_code > 599:
        raise ValueError("O código HTTP da auditoria é inválido.")

    return AuditEvent(
        event_id=str(uuid4()),
        event_type=clean_event_type[:80],
        occurred_at=datetime.now(timezone.utc),
        principal_id=principal_id,
        workflow_id=workflow_id,
        outcome=outcome,
        status_code=status_code,
        duration_ms=(
            max(round(duration_ms, 3), 0.0)
            if duration_ms is not None
            else None
        ),
        details=_sanitize_details(details),
    )
