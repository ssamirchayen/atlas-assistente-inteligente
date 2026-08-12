from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.workflow.cancellation import (
    CancellationSnapshot,
    CancellationToken,
)


@dataclass(slots=True)
class WorkflowContext:
    """
    Armazena informações compartilhadas entre
    as etapas de um workflow.
    """

    data: dict[str, Any] = field(default_factory=dict)

    results: list[Any] = field(default_factory=list)

    history: list[dict[str, Any]] = field(default_factory=list)

    cancellation: CancellationToken = field(
        default_factory=CancellationToken
    )

    def set(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.data[key] = value

    def get(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        return self.data.get(key, default)

    def exists(
        self,
        key: str,
    ) -> bool:
        return key in self.data

    def remove(
        self,
        key: str,
    ) -> None:
        self.data.pop(key, None)

    def clear(self) -> None:
        """
        Limpa os dados transitórios do contexto.

        O estado de cancelamento não é reiniciado automaticamente,
        pois um cancelamento solicitado deve continuar válido durante
        todo o ciclo de vida da execução.
        """

        self.data.clear()
        self.results.clear()
        self.history.clear()

    def update(
        self,
        values: dict[str, Any],
    ) -> None:
        self.data.update(values)

    def set_result(
        self,
        result: Any,
    ) -> None:
        self.results.append(result)

    def last_result(self) -> Any | None:
        if not self.results:
            return None

        return self.results[-1]

    def add_history(
        self,
        event: str,
        **metadata: Any,
    ) -> None:
        self.history.append(
            {
                "event": event,
                **metadata,
            }
        )

    def cancel(
        self,
        *,
        reason: str | None = None,
        requested_by: str | None = None,
    ) -> bool:
        """
        Solicita o cancelamento do workflow.

        Retorna ``True`` quando esta chamada realizou o cancelamento
        e ``False`` quando ele já havia sido solicitado anteriormente.
        """

        changed = self.cancellation.cancel(
            reason=reason,
            requested_by=requested_by,
        )

        if changed:
            snapshot = self.cancellation.snapshot()

            self.add_history(
                "workflow_cancellation_requested",
                reason=snapshot.reason,
                requested_by=snapshot.requested_by,
                cancelled_at=(
                    snapshot.cancelled_at.isoformat()
                    if snapshot.cancelled_at is not None
                    else None
                ),
            )

        return changed

    def is_cancelled(self) -> bool:
        """Retorna ``True`` quando houve solicitação de cancelamento."""

        return self.cancellation.is_cancelled()

    def throw_if_cancelled(self) -> None:
        """Interrompe a execução quando o contexto estiver cancelado."""

        self.cancellation.throw_if_cancelled()

    def cancellation_snapshot(self) -> CancellationSnapshot:
        """Retorna uma cópia imutável dos dados de cancelamento."""

        return self.cancellation.snapshot()

    def as_dict(self) -> dict[str, Any]:
        return dict(self.data)
