from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from atlas.planner.results import ExecutionResult


@dataclass(slots=True)
class WorkflowResult:
    """
    Resultado final da execução de um workflow.

    Não executa nenhuma etapa.
    Apenas consolida o resultado produzido pelo WorkflowEngine.
    """

    success: bool

    completed_steps: int
    total_steps: int

    results: list[ExecutionResult] = field(default_factory=list)

    error: str | None = None

    cancelled: bool = False
    cancellation_reason: str | None = None
    cancellation_requested_by: str | None = None
    cancelled_at: datetime | None = None
    cancelled_step: str | None = None

    @property
    def failed(self) -> bool:
        return not self.success

    @property
    def progress(self) -> float:
        if self.total_steps == 0:
            return 1.0

        return self.completed_steps / self.total_steps

    @property
    def is_complete(self) -> bool:
        return (
            self.success
            and self.completed_steps == self.total_steps
        )

    # ------------------------------------------------------------------
    # Compatibilidade temporária
    # ------------------------------------------------------------------

    @property
    def completed_actions(self) -> int:
        return self.completed_steps

    @property
    def total_actions(self) -> int:
        return self.total_steps

    # ------------------------------------------------------------------
    # Fábricas
    # ------------------------------------------------------------------

    @classmethod
    def success_result(
        cls,
        results: list[ExecutionResult],
    ) -> WorkflowResult:
        return cls(
            success=True,
            completed_steps=len(results),
            total_steps=len(results),
            results=results,
        )

    @classmethod
    def failed_result(
        cls,
        *,
        completed_steps: int,
        total_steps: int,
        results: list[ExecutionResult],
        error: str,
    ) -> WorkflowResult:
        return cls(
            success=False,
            completed_steps=completed_steps,
            total_steps=total_steps,
            results=results,
            error=error,
        )

    @classmethod
    def cancelled_result(
        cls,
        *,
        completed_steps: int,
        total_steps: int,
        results: list[ExecutionResult],
        reason: str | None,
        requested_by: str | None,
        cancelled_at: datetime | None,
        cancelled_step: str | None,
    ) -> WorkflowResult:
        return cls(
            success=False,
            completed_steps=completed_steps,
            total_steps=total_steps,
            results=results,
            error=reason or "O workflow foi cancelado.",
            cancelled=True,
            cancellation_reason=reason,
            cancellation_requested_by=requested_by,
            cancelled_at=cancelled_at,
            cancelled_step=cancelled_step,
        )
