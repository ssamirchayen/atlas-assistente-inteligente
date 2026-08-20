"""Modelos imutáveis da sessão operacional do Atlas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class SessionStatus(StrEnum):
    """Estados possíveis de uma sessão operacional."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.CANCELLED,
        }


class TimelineEventType(StrEnum):
    """Eventos persistidos na linha do tempo operacional."""

    SESSION_STARTED = "session.started"
    SESSION_RESUMED = "session.resumed"
    SESSION_PAUSED = "session.paused"
    SESSION_COMPLETED = "session.completed"
    SESSION_FAILED = "session.failed"
    SESSION_CANCELLED = "session.cancelled"
    COMMAND_RECEIVED = "command.received"
    COMMAND_UNHANDLED = "command.unhandled"
    COMMAND_COMPLETED = "command.completed"
    COMMAND_FAILED = "command.failed"
    TASK_SCHEDULED = "task.scheduled"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"
    WORKFLOW_RESUME_CONFIRMATION_REQUIRED = (
        "workflow.resume_confirmation_required"
    )
    WORKFLOW_RESUME_BLOCKED = "workflow.resume_blocked"
    WORKFLOW_RESUMED = "workflow.resumed"
    STEP_COMPLETED = "step.completed"
    STEP_FAILED = "step.failed"


@dataclass(frozen=True, slots=True)
class OperationalSession:
    """Snapshot persistente de uma sessão de trabalho do Atlas."""

    session_id: str
    user_id: str
    title: str
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    context: Mapping[str, Any]

    @property
    def is_resumable(self) -> bool:
        return self.status in {
            SessionStatus.ACTIVE,
            SessionStatus.PAUSED,
        }

    def as_dict(self) -> dict[str, Any]:
        """Retorna uma representação segura para API, logs e testes."""

        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ended_at": (
                self.ended_at.isoformat()
                if self.ended_at is not None
                else None
            ),
            "context": dict(self.context),
        }


@dataclass(frozen=True, slots=True)
class OperationalEvent:
    """Registro imutável de uma ocorrência dentro de uma sessão."""

    event_id: str
    session_id: str
    sequence: int
    event_type: TimelineEventType
    occurred_at: datetime
    message: str
    workflow_id: str | None
    action_type: str | None
    details: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Retorna dados serializáveis para API, GUI e diagnóstico."""

        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat(),
            "message": self.message,
            "workflow_id": self.workflow_id,
            "action_type": self.action_type,
            "details": dict(self.details),
        }
