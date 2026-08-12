from __future__ import annotations

import re
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from atlas.core.config import ATLAS_NAME
from atlas.core.controller import AtlasController
from atlas.scheduler.worker import SchedulerWorker

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from atlas.core.kernel import AtlasKernel


@dataclass(frozen=True, slots=True)
class GuiCommandResult:
    """Resposta estruturada enviada pelo backend para a interface."""

    message: str
    source: str
    success: bool = True
    action_count: int = 0
    cancelled: bool = False
    should_close: bool = False


class SerialCommandRunner:
    """Executa todos os comandos na mesma thread persistente."""

    def __init__(
        self,
        handler: Callable[[str], GuiCommandResult],
    ) -> None:
        self._handler = handler
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="atlas-gui-command",
        )
        self._closed = False

    def submit(self, command: str) -> Future[GuiCommandResult]:
        if self._closed:
            raise RuntimeError("O executor de comandos já foi encerrado.")

        return self._executor.submit(self._handler, command)

    def close(self, cleanup: Callable[[], None] | None = None) -> None:
        if self._closed:
            return

        self._closed = True

        if cleanup is not None:
            self._executor.submit(cleanup)

        self._executor.shutdown(
            wait=False,
            cancel_futures=False,
        )


class AtlasGuiService:
    """Conecta a interface ao mesmo núcleo usado pelo modo principal."""

    def __init__(
        self,
        kernel: AtlasKernel | None = None,
        controller: AtlasController | None = None,
        *,
        enable_scheduler: bool = True,
    ) -> None:
        if kernel is None:
            from atlas.core.kernel import AtlasKernel

            kernel = AtlasKernel()

        self.kernel = kernel
        self.controller = controller or AtlasController(kernel)
        self.scheduler_worker = (
            SchedulerWorker(
                scheduler=self.kernel.scheduler,
                executor=lambda job: self.controller.execute(job.command),
            )
            if enable_scheduler
            else None
        )
        self._started = False

    def start(self) -> None:
        if self.scheduler_worker is None or self._started:
            return

        self.scheduler_worker.start()
        self._started = True

    def execute(self, command: str) -> GuiCommandResult:
        clean_command = command.strip()

        if not clean_command:
            return GuiCommandResult(
                message="Digite um comando para o Atlas.",
                source="system",
                success=False,
            )

        execution_command = self._strip_optional_wake_word(clean_command)

        if not execution_command:
            return GuiCommandResult(
                message="Pode dizer. O que você quer que eu faça?",
                source="system",
                success=False,
            )

        normalized = execution_command.lower()

        if normalized in {"sair", "fechar atlas", "encerrar atlas"}:
            return GuiCommandResult(
                message="Encerrando o Atlas. Até mais, Ssamir.",
                source="system",
                should_close=True,
            )

        if normalized in {
            "limpar contexto",
            "apagar contexto",
            "esquecer conversa",
        }:
            self.kernel.context.clear()
            return GuiCommandResult(
                message="O contexto da conversa foi apagado.",
                source="system",
            )

        self._save_last_command(clean_command)

        priority_result = self.kernel.router.route_priority(execution_command)

        if priority_result.handled:
            self._add_turn(clean_command, priority_result.message)
            return GuiCommandResult(
                message=priority_result.message,
                source="skill",
            )

        actions, results = self.controller.execute(execution_command)

        if results:
            message = " ".join(str(result) for result in results)
            cancelled = any(
                result.error_code == "workflow_cancelled"
                for result in results
            )
            success = all(result.success for result in results)
            self._add_turn(clean_command, message)

            return GuiCommandResult(
                message=message,
                source=("scheduler" if not actions else "workflow"),
                success=success,
                action_count=len(actions),
                cancelled=cancelled,
            )

        route_result = self.kernel.router.route(execution_command)

        if route_result.handled:
            self._add_turn(clean_command, route_result.message)
            return GuiCommandResult(
                message=route_result.message,
                source="skill",
            )

        memory_context = self.kernel.memory.context(execution_command)
        conversation_context = self.kernel.context.get_recent_history()
        combined_context = self._combine_contexts(
            memory_context,
            conversation_context,
        )
        answer = self.kernel.brain.respond(
            execution_command,
            combined_context,
        )
        self._add_turn(clean_command, answer)

        return GuiCommandResult(
            message=answer,
            source="brain",
        )

    def cancel(self) -> bool:
        return self.controller.cancel_active_workflow(
            reason="Cancelado pela interface",
            requested_by="Ssamir",
        )

    def close(self) -> None:
        if self.scheduler_worker is not None and self._started:
            self.scheduler_worker.stop()
            self._started = False

        memory = getattr(self.kernel, "memory", None)
        close_memory = getattr(memory, "close", None)

        if callable(close_memory):
            close_memory()

        automation = getattr(self.kernel, "automation", None)
        close_automation = getattr(automation, "close", None)

        if callable(close_automation):
            close_automation()

    def _save_last_command(self, command: str) -> None:
        session = getattr(self.kernel, "session", None)
        save_last_command = getattr(session, "save_last_command", None)

        if callable(save_last_command):
            save_last_command(command)

    def _add_turn(self, command: str, response: str) -> None:
        self.kernel.context.add_turn(command, response)
        self._capture_user_memory(command)

    def _capture_user_memory(self, command: str) -> None:
        auto_memory = getattr(self.kernel, "auto_memory", None)
        capture = getattr(auto_memory, "capture", None)

        if not callable(capture):
            return

        try:
            capture(command)
        except Exception:
            _LOGGER.exception(
                "Falha não bloqueante ao capturar memória automática"
            )

    @staticmethod
    def _combine_contexts(*contexts: Any) -> str:
        return "\n\n".join(
            str(context).strip()
            for context in contexts
            if context and str(context).strip()
        )

    @staticmethod
    def _strip_optional_wake_word(command: str) -> str:
        """Remove a palavra de ativação sem alterar o restante do texto."""

        wake_names = {
            ATLAS_NAME.strip(),
            "Atlas",
            "Atras",
        }
        wake_expression = "|".join(
            re.escape(name)
            for name in wake_names
            if name
        )
        prefix = (
            r"^\s*(?:(?:ok|ei|ol[áa]|al[oô]|por favor)\s+)?"
            rf"(?:{wake_expression})\b[\s,;:!?.-]*"
        )

        return re.sub(
            prefix,
            "",
            command,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
