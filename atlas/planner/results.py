from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ExecutionResult:
    """Resultado estruturado da execução de uma ação do Atlas."""

    success: bool
    action_type: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False
    duration: float = 0.0
    attempts: int = 1
    index: int | None = None
    total: int | None = None

    def __str__(self) -> str:
        prefix = ""

        if self.index is not None and self.total is not None:
            prefix = f"[{self.index}/{self.total}] "

        duration = ""

        if self.duration > 0:
            duration = f" ({self.duration:.2f}s)"

        attempts_text = ""

        if self.attempts > 1:
            attempts_text = f" após {self.attempts} tentativas"

        return f"{prefix}{self.message}{attempts_text}{duration}"

    @classmethod
    def ok(
        cls,
        action_type: str,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        duration: float = 0.0,
        attempts: int = 1,
    ) -> ExecutionResult:
        return cls(
            success=True,
            action_type=action_type,
            message=message,
            data=data or {},
            duration=duration,
            attempts=attempts,
        )

    @classmethod
    def fail(
        cls,
        action_type: str,
        message: str,
        *,
        error_code: str,
        retryable: bool = False,
        data: dict[str, Any] | None = None,
        duration: float = 0.0,
        attempts: int = 1,
    ) -> ExecutionResult:
        return cls(
            success=False,
            action_type=action_type,
            message=message,
            data=data or {},
            error_code=error_code,
            retryable=retryable,
            duration=duration,
            attempts=attempts,
        )