"""Planejamento determinístico e seguro da retomada de workflows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from atlas.planner.actions import Action
from atlas.session.models import (
    OperationalEvent,
    OperationalSession,
    TimelineEventType,
)


_WORKFLOW_TERMINAL_EVENT_TYPES = frozenset(
    {
        TimelineEventType.WORKFLOW_COMPLETED,
        TimelineEventType.WORKFLOW_FAILED,
        TimelineEventType.WORKFLOW_CANCELLED,
        TimelineEventType.WORKFLOW_RESUMED,
    }
)

_SAFE_ACTION_TYPES = frozenset(
    {
        "browser.current_url",
        "browser.page_title",
        "helpdesk.diagnose",
        "hr.generate_document",
        "sales.compose_message",
        "system.wait",
    }
)

_BLOCKED_ACTION_TYPES = frozenset(
    {
        "browser.close",
        "browser.fill_input",
        "file.delete",
        "keyboard.write",
        "window.close",
        "window.close_title",
    }
)

_REDACTED_VALUE = "[ATLAS_REDACTED]"
_SENSITIVE_PARAMETER_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "secret",
        "token",
    }
)


class ResumptionRisk(StrEnum):
    """Nível de risco de repetir uma ação após uma interrupção."""

    SAFE = "safe"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


class ResumptionStatus(StrEnum):
    """Decisão consolidada para um workflow interrompido."""

    NOT_AVAILABLE = "not_available"
    READY = "ready"
    CONFIRMATION_REQUIRED = "confirmation_required"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ResumableStep:
    """Etapa pendente reconstruída a partir da linha do tempo."""

    step_index: int
    action_type: str
    parameters: Mapping[str, Any]
    risk: ResumptionRisk
    reason: str

    @property
    def step_number(self) -> int:
        return self.step_index + 1

    def to_action(self) -> Action:
        return Action(
            type=self.action_type,
            parameters=dict(self.parameters),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "step_number": self.step_number,
            "action_type": self.action_type,
            "parameters": dict(self.parameters),
            "risk": self.risk.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ResumptionPlan:
    """Plano imutável que descreve se e como uma retomada pode ocorrer."""

    session_id: str
    status: ResumptionStatus
    reason: str
    source_workflow_id: str | None = None
    source_sequence: int | None = None
    total_steps: int = 0
    completed_step_indexes: tuple[int, ...] = ()
    remaining_steps: tuple[ResumableStep, ...] = ()
    confirmation_token: str | None = None

    @property
    def requires_confirmation(self) -> bool:
        return self.status is ResumptionStatus.CONFIRMATION_REQUIRED

    @property
    def can_resume(self) -> bool:
        return self.status in {
            ResumptionStatus.READY,
            ResumptionStatus.CONFIRMATION_REQUIRED,
        }

    def to_actions(self) -> list[Action]:
        return [step.to_action() for step in self.remaining_steps]

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "reason": self.reason,
            "source_workflow_id": self.source_workflow_id,
            "source_sequence": self.source_sequence,
            "total_steps": self.total_steps,
            "completed_step_indexes": list(self.completed_step_indexes),
            "remaining_steps": [
                step.as_dict() for step in self.remaining_steps
            ],
            "confirmation_token": self.confirmation_token,
            "requires_confirmation": self.requires_confirmation,
            "can_resume": self.can_resume,
        }

    @classmethod
    def not_available(
        cls,
        session_id: str,
        reason: str = "Não há workflow interrompido para retomar.",
    ) -> ResumptionPlan:
        return cls(
            session_id=session_id,
            status=ResumptionStatus.NOT_AVAILABLE,
            reason=reason,
        )


class WorkflowResumptionPlanner:
    """Reconstrói o ponto de retomada sem executar nenhuma ação."""

    def build(
        self,
        session: OperationalSession,
        events: Iterable[OperationalEvent],
    ) -> ResumptionPlan:
        ordered_events = tuple(sorted(events, key=lambda item: item.sequence))
        started = self._find_latest_open_workflow(ordered_events)

        if started is None or started.workflow_id is None:
            return ResumptionPlan.not_available(session.session_id)

        actions = self._deserialize_actions(started.details.get("actions"))

        if actions is None:
            return ResumptionPlan(
                session_id=session.session_id,
                status=ResumptionStatus.BLOCKED,
                reason=(
                    "O workflow interrompido não possui um plano de ações "
                    "completo e não pode ser reconstruído com segurança."
                ),
                source_workflow_id=started.workflow_id,
                source_sequence=started.sequence,
            )

        if not actions:
            return ResumptionPlan(
                session_id=session.session_id,
                status=ResumptionStatus.BLOCKED,
                reason="O workflow interrompido não possui etapas válidas.",
                source_workflow_id=started.workflow_id,
                source_sequence=started.sequence,
            )

        completed_indexes = self._completed_step_indexes(
            ordered_events,
            started=started,
            total_steps=len(actions),
        )
        remaining_steps = tuple(
            self._build_step(index, action)
            for index, action in enumerate(actions)
            if index not in completed_indexes
        )

        if not remaining_steps:
            return ResumptionPlan(
                session_id=session.session_id,
                status=ResumptionStatus.BLOCKED,
                reason=(
                    "Todas as etapas foram registradas como concluídas; "
                    "a execução precisa apenas de reconciliação manual."
                ),
                source_workflow_id=started.workflow_id,
                source_sequence=started.sequence,
                total_steps=len(actions),
                completed_step_indexes=tuple(sorted(completed_indexes)),
            )

        status, reason = self._consolidate_decision(remaining_steps)
        token = self._confirmation_token(
            session_id=session.session_id,
            workflow_id=started.workflow_id,
            source_sequence=started.sequence,
            completed_indexes=completed_indexes,
            remaining_steps=remaining_steps,
        )
        return ResumptionPlan(
            session_id=session.session_id,
            status=status,
            reason=reason,
            source_workflow_id=started.workflow_id,
            source_sequence=started.sequence,
            total_steps=len(actions),
            completed_step_indexes=tuple(sorted(completed_indexes)),
            remaining_steps=remaining_steps,
            confirmation_token=token,
        )

    @staticmethod
    def classify(action_type: str) -> tuple[ResumptionRisk, str]:
        clean_type = action_type.strip()

        if clean_type in _BLOCKED_ACTION_TYPES:
            return (
                ResumptionRisk.BLOCKED,
                "Ação destrutiva ou de encerramento não pode ser repetida.",
            )

        if clean_type in _SAFE_ACTION_TYPES:
            return (
                ResumptionRisk.SAFE,
                "Ação local sem efeito externo irreversível.",
            )

        return (
            ResumptionRisk.CONFIRMATION_REQUIRED,
            "A ação pode alterar estado externo e exige confirmação.",
        )

    @classmethod
    def serialize_actions(cls, actions: Iterable[Action]) -> list[dict[str, Any]]:
        """Serializa o plano sem persistir credenciais conhecidas."""

        return [
            {
                "type": action.type,
                "parameters": cls._sanitize_mapping(action.parameters),
            }
            for action in actions
        ]

    @classmethod
    def _build_step(cls, index: int, action: Action) -> ResumableStep:
        if cls._contains_redacted_value(action.parameters):
            risk = ResumptionRisk.BLOCKED
            reason = (
                "A etapa continha dado sensível que não foi persistido e "
                "precisa ser recriada pelo usuário."
            )
        else:
            risk, reason = cls.classify(action.type)
        return ResumableStep(
            step_index=index,
            action_type=action.type,
            parameters=dict(action.parameters),
            risk=risk,
            reason=reason,
        )

    @staticmethod
    def _find_latest_open_workflow(
        events: tuple[OperationalEvent, ...],
    ) -> OperationalEvent | None:
        terminal_ids = {
            event.workflow_id
            for event in events
            if event.workflow_id
            and event.event_type in _WORKFLOW_TERMINAL_EVENT_TYPES
        }
        return next(
            (
                event
                for event in reversed(events)
                if event.workflow_id
                and event.event_type is TimelineEventType.WORKFLOW_STARTED
                and event.workflow_id not in terminal_ids
            ),
            None,
        )

    @staticmethod
    def _deserialize_actions(raw_actions: Any) -> list[Action] | None:
        if not isinstance(raw_actions, list):
            return None

        actions: list[Action] = []

        for raw_action in raw_actions:
            if not isinstance(raw_action, Mapping):
                return None

            action_type = raw_action.get("type")
            parameters = raw_action.get("parameters", {})

            if not isinstance(action_type, str) or not action_type.strip():
                return None

            if not isinstance(parameters, Mapping):
                return None

            actions.append(
                Action(
                    type=action_type.strip(),
                    parameters=dict(parameters),
                )
            )

        return actions

    @staticmethod
    def _completed_step_indexes(
        events: tuple[OperationalEvent, ...],
        *,
        started: OperationalEvent,
        total_steps: int,
    ) -> frozenset[int]:
        completed: set[int] = set()

        for event in events:
            if event.sequence <= started.sequence:
                continue

            if event.workflow_id != started.workflow_id:
                continue

            if event.event_type is not TimelineEventType.STEP_COMPLETED:
                continue

            step_index = event.details.get("step_index")

            if (
                isinstance(step_index, int)
                and not isinstance(step_index, bool)
                and 0 <= step_index < total_steps
            ):
                completed.add(step_index)

        return frozenset(completed)

    @staticmethod
    def _consolidate_decision(
        remaining_steps: tuple[ResumableStep, ...],
    ) -> tuple[ResumptionStatus, str]:
        if any(step.risk is ResumptionRisk.BLOCKED for step in remaining_steps):
            return (
                ResumptionStatus.BLOCKED,
                "O plano contém ação destrutiva ou de encerramento e foi "
                "bloqueado para evitar repetição indevida.",
            )

        if any(
            step.risk is ResumptionRisk.CONFIRMATION_REQUIRED
            for step in remaining_steps
        ):
            return (
                ResumptionStatus.CONFIRMATION_REQUIRED,
                "A retomada exige confirmação porque pode alterar estado "
                "externo.",
            )

        return (
            ResumptionStatus.READY,
            "As etapas restantes podem ser retomadas com segurança.",
        )

    @staticmethod
    def _confirmation_token(
        *,
        session_id: str,
        workflow_id: str,
        source_sequence: int,
        completed_indexes: frozenset[int],
        remaining_steps: tuple[ResumableStep, ...],
    ) -> str:
        payload = {
            "session_id": session_id,
            "workflow_id": workflow_id,
            "source_sequence": source_sequence,
            "completed_indexes": sorted(completed_indexes),
            "remaining_steps": [
                {
                    "step_index": step.step_index,
                    "action_type": step.action_type,
                    "parameters": dict(step.parameters),
                }
                for step in remaining_steps
            ],
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return sha256(serialized.encode("utf-8")).hexdigest()[:20]

    @classmethod
    def _sanitize_mapping(
        cls,
        values: Mapping[str, Any],
    ) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}

        for key, value in values.items():
            clean_key = str(key)

            if clean_key.casefold() in _SENSITIVE_PARAMETER_NAMES:
                sanitized[clean_key] = _REDACTED_VALUE
                continue

            sanitized[clean_key] = cls._sanitize_value(value)

        return sanitized

    @classmethod
    def _sanitize_value(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return cls._sanitize_mapping(value)

        if isinstance(value, (list, tuple)):
            return [cls._sanitize_value(item) for item in value]

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        return str(value)

    @classmethod
    def _contains_redacted_value(cls, value: Any) -> bool:
        if value == _REDACTED_VALUE:
            return True

        if isinstance(value, Mapping):
            return any(
                cls._contains_redacted_value(item)
                for item in value.values()
            )

        if isinstance(value, (list, tuple)):
            return any(cls._contains_redacted_value(item) for item in value)

        return False
