"""Auditoria redigida e local do Atlas Vision Etapa 16."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable


@dataclass(frozen=True, slots=True)
class VisionAuditEvent:
    timestamp: str
    operation: str
    outcome: str
    reason_code: str
    action_count: int
    duration_ms: int
    context_kind: str


class VisionAuditTrail:
    """Registra apenas metadados operacionais, nunca conteúdo ou tokens."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._events: list[VisionAuditEvent] = []
        self._lock = RLock()

    @staticmethod
    def _context_kind(context_token: str | None) -> str:
        if not context_token:
            return "none"
        prefix = context_token.partition(":")[0].casefold()
        return prefix if prefix in {"dom", "uia"} else "other"

    def record(
        self,
        *,
        operation: str,
        success: bool,
        reason_code: str | None,
        action_count: int,
        duration_ms: int,
        context_token: str | None = None,
    ) -> VisionAuditEvent:
        event = VisionAuditEvent(
            timestamp=self._clock().astimezone(timezone.utc).isoformat(),
            operation=operation,
            outcome="success" if success else "failed",
            reason_code=reason_code or "none",
            action_count=max(0, int(action_count)),
            duration_ms=max(0, int(duration_ms)),
            context_kind=self._context_kind(context_token),
        )

        with self._lock:
            self._events.append(event)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(
                            asdict(event),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
                    )
        return event

    def snapshot(self) -> tuple[VisionAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

