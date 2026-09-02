"""Privacy-preserving persistent audit for Atlas Edge governance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Callable, Protocol
from uuid import uuid4

from atlas.edge.governance import EdgeAction, EdgePrincipal
from atlas.edge.models import normalize_organization_id


_EVENT_ID = re.compile(r"^edgeaudit_[a-f0-9]{32}$")
_DEVICE_ID = re.compile(r"^edge_[a-f0-9]{32}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class EdgeAuditOutcome(StrEnum):
    AUTHORIZED = "authorized"
    DENIED = "denied"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class EdgeAuditEvent:
    """Structured evidence with hashes and safe IDs only."""

    organization_id: str
    device_id: str
    actor_hash: str
    actor_role: str
    action: EdgeAction
    outcome: EdgeAuditOutcome
    reason_code: str
    occurred_at: datetime
    target_id: str | None = None
    plan_digest: str | None = None
    dry_run: bool | None = None
    event_id: str = field(default_factory=lambda: f"edgeaudit_{uuid4().hex}")

    def __post_init__(self) -> None:
        if not _EVENT_ID.fullmatch(self.event_id):
            raise ValueError("O identificador do evento de auditoria é inválido.")
        if not _DEVICE_ID.fullmatch(self.device_id):
            raise ValueError("O dispositivo do evento de auditoria é inválido.")
        if not _DIGEST.fullmatch(self.actor_hash):
            raise ValueError("O responsável da auditoria deve estar anonimizado.")
        if not _SAFE_CODE.fullmatch(self.actor_role):
            raise ValueError("A função da auditoria é inválida.")
        if not isinstance(self.action, EdgeAction):
            raise TypeError("action deve ser EdgeAction.")
        if not isinstance(self.outcome, EdgeAuditOutcome):
            raise TypeError("outcome deve ser EdgeAuditOutcome.")
        if not _SAFE_CODE.fullmatch(self.reason_code):
            raise ValueError("O código do resultado da auditoria é inválido.")
        if self.occurred_at.tzinfo is None:
            raise ValueError("O evento de auditoria deve possuir fuso horário.")
        if self.target_id is not None and not _SAFE_TARGET.fullmatch(
            self.target_id
        ):
            raise ValueError("O alvo da auditoria não é um ID seguro.")
        if self.plan_digest is not None and not _DIGEST.fullmatch(
            self.plan_digest
        ):
            raise ValueError("O plano da auditoria deve ser um SHA-256.")
        object.__setattr__(
            self,
            "organization_id",
            normalize_organization_id(self.organization_id),
        )
        object.__setattr__(
            self,
            "occurred_at",
            self.occurred_at.astimezone(timezone.utc),
        )


class EdgeAuditTrail(Protocol):
    def record(self, event: EdgeAuditEvent) -> None: ...

    def query(
        self,
        organization_id: str,
        *,
        limit: int = 100,
    ) -> tuple[EdgeAuditEvent, ...]: ...


class InMemoryEdgeAuditTrail:
    """Deterministic audit implementation for tests and local pilots."""

    def __init__(self) -> None:
        self.events: list[EdgeAuditEvent] = []

    def record(self, event: EdgeAuditEvent) -> None:
        self.events.append(event)

    def query(
        self,
        organization_id: str,
        *,
        limit: int = 100,
    ) -> tuple[EdgeAuditEvent, ...]:
        organization_id = normalize_organization_id(organization_id)
        _validate_limit(limit)
        return tuple(
            event
            for event in reversed(self.events)
            if event.organization_id == organization_id
        )[:limit]


class SqliteEdgeAuditTrail:
    """Bounded SQLite audit isolated by organization."""

    def __init__(
        self,
        path: Path,
        *,
        retention_days: int = 90,
        max_events: int = 10_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if retention_days <= 0 or max_events <= 0:
            raise ValueError("Os limites da auditoria devem ser positivos.")
        self.path = Path(path)
        self._retention = timedelta(days=retention_days)
        self._max_events = max_events
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record(self, event: EdgeAuditEvent) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO edge_audit (
                    event_id, occurred_at, organization_id, device_id,
                    actor_hash, actor_role, action, outcome, reason_code,
                    target_id, plan_digest, dry_run
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.occurred_at.isoformat(),
                    event.organization_id,
                    event.device_id,
                    event.actor_hash,
                    event.actor_role,
                    event.action.value,
                    event.outcome.value,
                    event.reason_code,
                    event.target_id,
                    event.plan_digest,
                    None if event.dry_run is None else int(event.dry_run),
                ),
            )
            self._prune(connection)

    def query(
        self,
        organization_id: str,
        *,
        limit: int = 100,
    ) -> tuple[EdgeAuditEvent, ...]:
        organization_id = normalize_organization_id(organization_id)
        _validate_limit(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, occurred_at, organization_id, device_id,
                       actor_hash, actor_role, action, outcome, reason_code,
                       target_id, plan_digest, dry_run
                  FROM edge_audit
                 WHERE organization_id = ?
                 ORDER BY occurred_at DESC, rowid DESC
                 LIMIT ?
                """,
                (organization_id, limit),
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edge_audit (
                    event_id TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    actor_hash TEXT NOT NULL,
                    actor_role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    target_id TEXT,
                    plan_digest TEXT,
                    dry_run INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS edge_audit_org_time
                    ON edge_audit (organization_id, occurred_at DESC)
                """
            )

    def _prune(self, connection: sqlite3.Connection) -> None:
        cutoff = self._now() - self._retention
        connection.execute(
            "DELETE FROM edge_audit WHERE occurred_at < ?",
            (cutoff.isoformat(),),
        )
        connection.execute(
            """
            DELETE FROM edge_audit
             WHERE rowid IN (
                SELECT rowid FROM edge_audit
                 ORDER BY occurred_at DESC, rowid DESC
                 LIMIT -1 OFFSET ?
             )
            """,
            (self._max_events,),
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("O relógio da auditoria deve possuir fuso horário.")
        return value.astimezone(timezone.utc)


def build_edge_audit_event(
    principal: EdgePrincipal,
    *,
    device_id: str,
    action: EdgeAction,
    outcome: EdgeAuditOutcome,
    reason_code: str,
    occurred_at: datetime,
    target_id: str | None = None,
    plan_digest: str | None = None,
    dry_run: bool | None = None,
    organization_id: str | None = None,
) -> EdgeAuditEvent:
    return EdgeAuditEvent(
        organization_id=organization_id or principal.organization_id,
        device_id=device_id,
        actor_hash=principal.principal_hash,
        actor_role=principal.role.value,
        action=action,
        outcome=outcome,
        reason_code=reason_code,
        occurred_at=occurred_at,
        target_id=target_id,
        plan_digest=plan_digest,
        dry_run=dry_run,
    )


def _event_from_row(row: tuple[object, ...]) -> EdgeAuditEvent:
    raw_dry_run = row[11]
    return EdgeAuditEvent(
        event_id=str(row[0]),
        occurred_at=datetime.fromisoformat(str(row[1])),
        organization_id=str(row[2]),
        device_id=str(row[3]),
        actor_hash=str(row[4]),
        actor_role=str(row[5]),
        action=EdgeAction(str(row[6])),
        outcome=EdgeAuditOutcome(str(row[7])),
        reason_code=str(row[8]),
        target_id=None if row[9] is None else str(row[9]),
        plan_digest=None if row[10] is None else str(row[10]),
        dry_run=None if raw_dry_run is None else bool(raw_dry_run),
    )


def _validate_limit(limit: int) -> None:
    if limit <= 0 or limit > 500:
        raise ValueError("O limite da consulta deve ficar entre 1 e 500.")
