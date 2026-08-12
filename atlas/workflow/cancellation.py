from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock
from typing import Any


class WorkflowCancelledError(RuntimeError):
    """Indica que a execução de um workflow foi cancelada."""

    def __init__(
        self,
        reason: str | None = None,
        requested_by: str | None = None,
    ) -> None:
        self.reason = reason
        self.requested_by = requested_by

        message = "O workflow foi cancelado."

        if reason:
            message = f"{message} Motivo: {reason}"

        if requested_by:
            message = f"{message} Solicitado por: {requested_by}"

        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CancellationSnapshot:
    """Representação imutável do estado atual de cancelamento."""

    cancelled: bool
    reason: str | None
    requested_by: str | None
    cancelled_at: datetime | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "cancelled": self.cancelled,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "cancelled_at": (
                self.cancelled_at.isoformat()
                if self.cancelled_at is not None
                else None
            ),
        }


class CancellationToken:
    """
    Controla o cancelamento cooperativo de uma execução.

    O token é seguro para uso entre threads e pode ser compartilhado
    entre o WorkflowEngine, Executor, agentes e demais componentes.

    O cancelamento é idempotente: apenas a primeira solicitação altera
    os metadados do token. Chamadas posteriores retornam ``False``.
    """

    def __init__(self) -> None:
        self._event = Event()
        self._lock = Lock()
        self._reason: str | None = None
        self._requested_by: str | None = None
        self._cancelled_at: datetime | None = None

    def cancel(
        self,
        *,
        reason: str | None = None,
        requested_by: str | None = None,
    ) -> bool:
        """
        Solicita o cancelamento.

        Retorna ``True`` quando esta chamada realizou o cancelamento.
        Retorna ``False`` quando o token já estava cancelado.
        """

        normalized_reason = self._normalize_optional_text(reason)
        normalized_requested_by = self._normalize_optional_text(
            requested_by
        )

        with self._lock:
            if self._event.is_set():
                return False

            self._reason = normalized_reason
            self._requested_by = normalized_requested_by
            self._cancelled_at = datetime.now(timezone.utc)
            self._event.set()

            return True

    def is_cancelled(self) -> bool:
        """Retorna ``True`` quando o cancelamento foi solicitado."""

        return self._event.is_set()

    def throw_if_cancelled(self) -> None:
        """Lança ``WorkflowCancelledError`` quando estiver cancelado."""

        if not self.is_cancelled():
            return

        snapshot = self.snapshot()

        raise WorkflowCancelledError(
            reason=snapshot.reason,
            requested_by=snapshot.requested_by,
        )

    def wait(self, timeout: float | None = None) -> bool:
        """
        Aguarda uma solicitação de cancelamento.

        Retorna ``True`` quando o token foi cancelado dentro do tempo
        informado e ``False`` quando o tempo limite foi atingido.
        """

        if timeout is not None and timeout < 0:
            raise ValueError(
                "O tempo limite de espera não pode ser negativo."
            )

        return self._event.wait(timeout)

    def snapshot(self) -> CancellationSnapshot:
        """Retorna uma cópia consistente dos dados de cancelamento."""

        with self._lock:
            return CancellationSnapshot(
                cancelled=self._event.is_set(),
                reason=self._reason,
                requested_by=self._requested_by,
                cancelled_at=self._cancelled_at,
            )

    @property
    def reason(self) -> str | None:
        return self.snapshot().reason

    @property
    def requested_by(self) -> str | None:
        return self.snapshot().requested_by

    @property
    def cancelled_at(self) -> datetime | None:
        return self.snapshot().cancelled_at

    @staticmethod
    def _normalize_optional_text(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None
