from __future__ import annotations

import logging
from threading import Event
from time import monotonic

from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult

logger = logging.getLogger(__name__)


class Executor:
    def __init__(
        self,
        engine: AutomationEngine | None = None,
        *,
        max_retries: int = 2,
        retry_delay: float = 0.5,
    ) -> None:
        self.engine = engine or AutomationEngine()
        self._cancel_event = Event()

        if max_retries < 0:
            raise ValueError("max_retries não pode ser negativo.")

        if retry_delay < 0:
            raise ValueError("retry_delay não pode ser negativo.")

        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def cancel(self) -> None:
        """Solicita o cancelamento da execução atual."""
        self._cancel_event.set()
        logger.warning("Cancelamento solicitado.")

    def reset(self) -> None:
        """Limpa um cancelamento anterior."""
        self._cancel_event.clear()

    def execute(
        self,
        actions: list[Action],
        *,
        stop_on_error: bool = False,
    ) -> list[ExecutionResult]:
        self.reset()

        if not actions:
            return [
                ExecutionResult.fail(
                    "plan.empty",
                    "Nenhuma ação para executar.",
                    error_code="empty_plan",
                    retryable=False,
                )
            ]

        results: list[ExecutionResult] = []
        total = len(actions)

        logger.info("Executando plano com %d ações.", total)

        for index, action in enumerate(actions, start=1):
            if self._cancel_event.is_set():
                results.append(
                    ExecutionResult.fail(
                        action.type,
                        "Plano cancelado pelo usuário.",
                        error_code="cancelled",
                        retryable=False,
                        index=index,
                        total=total,
                    )
                )
                break

            logger.info("[%d/%d] Iniciando ação '%s'.", index, total, action.type)

            result = self._execute_with_retry(action)

            result.index = index
            result.total = total
            results.append(result)

            logger.info(
                (
                    "[%d/%d] concluída: success=%s "
                    "attempts=%d duration=%.2fs error_code=%s"
                ),
                index,
                total,
                result.success,
                result.attempts,
                result.duration,
                result.error_code,
            )

            if stop_on_error and not result.success:
                logger.warning(
                    "Execução interrompida após falha em '%s'.",
                    action.type,
                )
                break

        logger.info(
            "Plano finalizado: %d sucesso(s), %d falha(s).",
            sum(result.success for result in results),
            sum(not result.success for result in results),
        )

        return results

    def _execute_with_retry(self, action: Action) -> ExecutionResult:
        """
        Executa uma ação e repete apenas quando a falha for retryable.

        max_retries representa a quantidade de novas tentativas após
        a primeira execução.

        Exemplo:
            max_retries=2
            total máximo de execuções=3
        """
        maximum_attempts = self.max_retries + 1
        accumulated_duration = 0.0
        last_result: ExecutionResult | None = None

        for attempt in range(1, maximum_attempts + 1):
            if self._cancel_event.is_set():
                return ExecutionResult.fail(
                    action.type,
                    "Execução cancelada pelo usuário.",
                    error_code="cancelled",
                    retryable=False,
                    duration=accumulated_duration,
                    attempts=max(1, attempt - 1),
                )

            logger.info(
                "Executando '%s': tentativa %d de %d.",
                action.type,
                attempt,
                maximum_attempts,
            )

            started_at = monotonic()

            try:
                result = self.engine.execute(action)

            except Exception as error:
                logger.exception(
                    "Erro inesperado fora do AutomationEngine ao executar '%s'.",
                    action.type,
                )

                result = ExecutionResult.fail(
                    action.type,
                    f"Erro inesperado: {error}",
                    error_code="executor_unexpected_error",
                    retryable=True,
                )

            elapsed = monotonic() - started_at

            # O AutomationEngine já pode medir a duração.
            # Usamos o maior valor para evitar perder essa informação.
            execution_duration = max(result.duration, elapsed)
            accumulated_duration += execution_duration

            result.duration = accumulated_duration
            result.attempts = attempt
            last_result = result

            if result.success:
                if attempt > 1:
                    logger.info(
                        "Ação '%s' concluída na tentativa %d.",
                        action.type,
                        attempt,
                    )

                return result

            logger.warning(
                (
                    "Falha na ação '%s': tentativa=%d "
                    "retryable=%s error_code=%s"
                ),
                action.type,
                attempt,
                result.retryable,
                result.error_code,
            )

            if not result.retryable:
                return result

            if attempt >= maximum_attempts:
                logger.error(
                    "Ação '%s' falhou após %d tentativa(s).",
                    action.type,
                    attempt,
                )
                return result

            logger.info(
                "Nova tentativa de '%s' em %.2f segundo(s).",
                action.type,
                self.retry_delay,
            )

            # Event.wait permite interromper imediatamente durante a espera.
            cancelled_during_wait = self._cancel_event.wait(
                timeout=self.retry_delay
            )

            if cancelled_during_wait:
                return ExecutionResult.fail(
                    action.type,
                    "Execução cancelada durante a espera para nova tentativa.",
                    error_code="cancelled",
                    retryable=False,
                    duration=accumulated_duration,
                    attempts=attempt,
                )

        # Proteção defensiva. O fluxo normal sempre retorna dentro do loop.
        if last_result is not None:
            return last_result

        return ExecutionResult.fail(
            action.type,
            "A ação não pôde ser executada.",
            error_code="execution_not_started",
            retryable=False,
            attempts=1,
        )