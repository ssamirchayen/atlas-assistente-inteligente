from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from atlas.planner.results import ExecutionResult


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Task:
    description: str

    id: str = field(default_factory=lambda: str(uuid4()))

    status: TaskStatus = TaskStatus.PENDING

    created_at: datetime = field(
    default_factory=lambda: datetime.now(UTC)
    )
    started_at: datetime | None = None
    finished_at: datetime | None = None

    result: ExecutionResult | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def complete(self, result: ExecutionResult) -> None:
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.finished_at = datetime.now(UTC)

    def fail(self, result: ExecutionResult) -> None:
        self.status = TaskStatus.FAILED
        self.result = result
        self.finished_at = datetime.now(UTC)

    def cancel(self) -> None:
        self.status = TaskStatus.CANCELLED
        self.finished_at = datetime.now(UTC)