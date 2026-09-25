from __future__ import annotations

from concurrent.futures import Future, TimeoutError
from typing import Callable

from atlas.gui.service import GuiCommandResult

from .models import CopilotRequest, CopilotResponse

CommandSubmitter = Callable[[str], Future[GuiCommandResult]]


class NexyraCopilotBridge:
    """Adapta o runtime serial do Atlas ao painel Copilot do Nexyra."""

    def __init__(
        self,
        submitter: CommandSubmitter,
        *,
        timeout_seconds: float = 45.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("O timeout do Copilot precisa ser maior que zero.")
        self._submitter = submitter
        self._timeout_seconds = timeout_seconds

    def handle(self, payload: dict[str, object]) -> CopilotResponse:
        request = CopilotRequest.from_payload(payload)
        if not request.message:
            return CopilotResponse(
                ok=False,
                intent="empty_message",
                context=request.context,
                answer="Digite uma mensagem para o Atlas.",
                error="Mensagem vazia.",
            )

        try:
            future = self._submitter(request.message)
            result = future.result(timeout=self._timeout_seconds)
        except TimeoutError:
            return CopilotResponse(
                ok=False,
                intent="timeout",
                context=request.context,
                answer=(
                    "O Atlas ainda está processando essa solicitação. "
                    "Confira o Atlas antes de tentar novamente."
                ),
                error="Tempo limite excedido no bridge local.",
                requires_human_review=True,
            )
        except Exception as exc:  # pragma: no cover - defesa do boundary HTTP
            return CopilotResponse(
                ok=False,
                intent="atlas_unavailable",
                context=request.context,
                answer="O Atlas não conseguiu processar a solicitação.",
                error=str(exc),
                requires_human_review=True,
            )

        return CopilotResponse(
            ok=result.success,
            intent="atlas_command",
            context=request.context,
            answer=result.message,
            data={
                "source": result.source,
                "action_count": result.action_count,
                "cancelled": result.cancelled,
                "reason_code": result.reason_code,
                "requires_confirmation": result.requires_confirmation,
                "confirmation_token": result.confirmation_token,
            },
            error=None if result.success else result.message,
            requires_human_review=result.requires_confirmation,
        )
