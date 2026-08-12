from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class ScheduledJob:
    id: str = field(default_factory=lambda: str(uuid4()))
    title: str = ""
    command: str = ""

    run_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    repeat: str | None = None
    enabled: bool = True

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    last_run: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "command": self.command,
            "run_at": self.run_at.isoformat(),
            "repeat": self.repeat,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "last_run": (
                self.last_run.isoformat()
                if self.last_run is not None
                else None
            ),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> ScheduledJob:
        return cls(
            id=str(data["id"]),
            title=str(data.get("title", "")),
            command=str(data.get("command", "")),
            run_at=datetime.fromisoformat(
                str(data["run_at"])
            ),
            repeat=data.get("repeat"),
            enabled=bool(data.get("enabled", True)),
            created_at=datetime.fromisoformat(
                str(data["created_at"])
            ),
            last_run=(
                datetime.fromisoformat(
                    str(data["last_run"])
                )
                if data.get("last_run")
                else None
            ),
        )