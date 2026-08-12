from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from atlas.workflow.cancellation import (
    CancellationSnapshot,
    CancellationToken,
)
from atlas.workflow.context import WorkflowContext
from atlas.workflow.step import WorkflowStep


@dataclass(slots=True)
class WorkflowState:
    """
    Representa o estado atual da execução de um workflow.

    O WorkflowState acompanha a execução,
    mas não executa nenhuma etapa diretamente.
    """

    steps: list[WorkflowStep]

    current_index: int = 0

    completed_steps: list[WorkflowStep] = field(
        default_factory=list
    )

    skipped_steps: list[WorkflowStep] = field(
        default_factory=list
    )

    failed_steps: list[WorkflowStep] = field(
        default_factory=list
    )

    current_step: WorkflowStep | None = None

    finished: bool = False
    failed: bool = False

    error: str | None = None

    context: WorkflowContext = field(
        default_factory=WorkflowContext
    )

    cancelled_step: WorkflowStep | None = None
    cancelled_index: int | None = None

    @property
    def has_next(self) -> bool:
        if self.context.is_cancelled():
            self._apply_cancellation_state()
            return False

        return (
            not self.finished
            and self.current_index < len(self.steps)
        )

    @property
    def progress(self) -> float:
        if not self.steps:
            return 1.0

        processed = (
            len(self.completed_steps)
            + len(self.skipped_steps)
            + len(self.failed_steps)
        )

        return processed / len(self.steps)

    @property
    def cancelled(self) -> bool:
        return self.context.is_cancelled()

    @property
    def cancellation_reason(self) -> str | None:
        return self.context.cancellation_snapshot().reason

    @property
    def cancellation_requested_by(self) -> str | None:
        return self.context.cancellation_snapshot().requested_by

    @property
    def cancelled_at(self) -> datetime | None:
        return self.context.cancellation_snapshot().cancelled_at

    def cancellation_snapshot(self) -> CancellationSnapshot:
        return self.context.cancellation_snapshot()

    def next_step(self) -> WorkflowStep | None:
        if self.context.is_cancelled():
            self._apply_cancellation_state()
            return None

        if not self.has_next:
            self.current_step = None
            self.finished = True
            return None

        self.current_step = self.steps[self.current_index]

        return self.current_step

    def mark_completed(self) -> None:
        if self.context.is_cancelled():
            self._apply_cancellation_state()
            return

        if self.current_step is not None:
            self.completed_steps.append(
                self.current_step
            )

        self._advance()

    def mark_skipped(self) -> None:
        if self.context.is_cancelled():
            self._apply_cancellation_state()
            return

        if self.current_step is not None:
            self.skipped_steps.append(
                self.current_step
            )

        self._advance()

    def mark_failed(
        self,
        message: str,
    ) -> None:
        if self.context.is_cancelled():
            self._apply_cancellation_state()
            return

        if self.current_step is not None:
            self.failed_steps.append(
                self.current_step
            )

        self.fail(message)

    def cancel(
        self,
        *,
        reason: str | None = None,
        requested_by: str | None = None,
    ) -> bool:
        changed = self.context.cancel(
            reason=reason,
            requested_by=requested_by,
        )

        self._apply_cancellation_state()

        return changed

    def throw_if_cancelled(self) -> None:
        self.context.throw_if_cancelled()

    def _apply_cancellation_state(self) -> None:
        if not self.context.is_cancelled():
            return

        if self.cancelled_index is None:
            self.cancelled_index = self.current_index
            self.cancelled_step = self.current_step

        self.finished = True
        self.failed = False
        self.error = None

    def _advance(self) -> None:
        self.current_index += 1
        self.current_step = None

        if self.current_index >= len(self.steps):
            self.finished = True

    def fail(
        self,
        message: str,
    ) -> None:
        if self.context.is_cancelled():
            self._apply_cancellation_state()
            return

        self.failed = True
        self.finished = True
        self.error = message

    def reset(self) -> None:
        self.current_index = 0

        self.completed_steps.clear()
        self.skipped_steps.clear()
        self.failed_steps.clear()

        self.current_step = None

        self.finished = False
        self.failed = False

        self.error = None

        self.cancelled_step = None
        self.cancelled_index = None

        self.context.clear()
        self.context.cancellation = CancellationToken()

    # Compatibilidade temporária

    @property
    def metadata(self):
        return self.context.data

    @property
    def current_action(self):
        if self.current_step is None:
            return None

        return self.current_step.action

    @property
    def actions(self):
        return [
            step.action
            for step in self.steps
        ]

    @property
    def completed_actions(self):
        return [
            step.action
            for step in self.completed_steps
        ]
