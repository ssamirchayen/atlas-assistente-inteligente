from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.core.config import ATLAS_NAME, USER_NAME
from atlas.core.controller import AtlasController
from atlas.core.kernel import AtlasKernel
from atlas.scheduler.worker import SchedulerWorker
from atlas.utils.logging_setup import setup_logging
from atlas.utils.text import remove_wake_word


class AtlasApp:
    def __init__(self) -> None:
        self.logger = setup_logging()
        self.kernel = AtlasKernel()
        self.controller = AtlasController(self.kernel)
        self.scheduler_worker = SchedulerWorker(
            scheduler=self.kernel.scheduler,
            executor=lambda job: self.controller.execute(job.command),
        )

    def run(self) -> None:
        self.kernel.speech.say(
            f"{ATLAS_NAME} 2.0 iniciado. Olá, {USER_NAME}."
        )

        self._announce_previous_session()
        self.scheduler_worker.start()

        while True:
            try:
                command = self._listen_for_command()

                if command is None:
                    continue

                self.kernel.session.save_last_command(command)

                if self._should_exit(command):
                    self.scheduler_worker.stop()
                    break

                if self._process_system_command(command):
                    continue

                if self._process_priority_router(command):
                    continue

                # Comandos determinísticos devem ser oferecidos primeiro
                # ao Planner e aos agentes especializados. Isso evita que
                # o ReasoningEngine bloqueie ações diretas do navegador,
                # como "clique no primeiro resultado", com uma pergunta
                # de esclarecimento antes que o BrowserAgent possa agir.
                if self._process_planner(command):
                    continue

                if self._process_reasoning(command):
                    continue

                if self._process_router(command):
                    continue

                self._process_brain(command)

            except KeyboardInterrupt:
                print()
                self.scheduler_worker.stop()
                self.kernel.speech.say("Atlas encerrado.")
                break

            except Exception as exc:
                self.logger.exception(
                    "Erro no ciclo principal"
                )

                print(
                    f"[ERRO] {type(exc).__name__}: {exc}"
                )

                self.kernel.speech.say(
                    "Ocorreu um erro. "
                    "Registrei os detalhes no log."
                )

    def _listen_for_command(self) -> str | None:
        spoken = self.kernel.speech.listen()

        if not spoken:
            return None

        return self._prepare_command(spoken)

    def _should_exit(self, command: str) -> bool:
        exit_commands = {
            "sair",
            "encerrar",
            "encerrar atlas",
        }

        if command.lower().strip() not in exit_commands:
            return False

        self.kernel.speech.say(
            f"Até mais, {USER_NAME}."
        )

        return True

    def _process_system_command(
        self,
        command: str,
    ) -> bool:
        normalized = command.lower().strip()

        if normalized == "modo voz":
            if self.kernel.speech.enable_microphone():
                self.kernel.speech.say(
                    "Modo de voz ativado."
                )
            else:
                self.kernel.speech.say(
                    "Não consegui ativar o microfone."
                )

            return True

        if normalized == "modo texto":
            self.kernel.speech.disable_microphone()

            self.kernel.speech.say(
                "Modo de texto ativado."
            )

            return True

        if normalized == "ativar palavra de ativacao":
            self.kernel.wake_word_enabled = True

            self.kernel.speech.say(
                "Palavra de ativação habilitada."
            )

            return True

        if normalized == "desativar palavra de ativacao":
            self.kernel.wake_word_enabled = False

            self.kernel.speech.say(
                "Palavra de ativação desabilitada."
            )

            return True

        if normalized in {
            "limpar contexto",
            "apagar contexto",
            "esquecer conversa",
        }:
            self.kernel.context.clear()

            self.kernel.speech.say(
                "O contexto da conversa foi apagado."
            )

            return True

        if normalized in {
            "resumo da sessao",
            "ultima sessao",
            "onde paramos",
            "o que estavamos fazendo",
        }:
            self._process_session_summary(command)
            return True

        return False

    def _process_session_summary(
        self,
        command: str,
    ) -> None:
        session_summary = (
            self.kernel.session.get_summary()
        )

        answer = self.kernel.brain.respond(
            command,
            session_summary,
        )

        self.kernel.speech.say(answer)

        self._add_turn(command, answer)

    def _process_reasoning(
        self,
        command: str,
    ) -> bool:
        """
        Executa a nova camada de raciocínio.

        Retorna True quando o ReasoningEngine resolveu
        completamente o comando.

        Retorna False quando o comando deve continuar
        para Planner, Router ou Brain.
        """

        reasoner = getattr(
            self.kernel,
            "reasoner",
            None,
        )

        if reasoner is None:
            return False

        try:
            decision = reasoner.reason(command)
        except Exception as exc:
            self.logger.exception(
                "Erro no ReasoningEngine"
            )

            print(
                "[REASONING ERRO] "
                f"{type(exc).__name__}: {exc}"
            )

            # Em caso de erro no ReasoningEngine, o Atlas
            # continua funcionando pelo pipeline antigo.
            return False

        if decision is None:
            return False

        decision_name = self._get_decision_name(
            decision
        )

        print(
            f"[REASONING] {decision_name}"
        )

        if decision_name == "ASK":
            question = self._get_decision_message(
                decision
            )

            if not question:
                question = (
                    "Preciso de mais informações "
                    "para realizar esse comando."
                )

            self.kernel.speech.say(question)

            self._add_turn(command, question)

            return True

        if decision_name in {
            "EXECUTE",
            "SEARCH_BROWSER",
        }:
            # O Planner continua responsável por transformar
            # a decisão em ações executáveis.
            return False

        if decision_name == "CHAT":
            # Conversas seguem para o Brain.
            return False

        # Decisões desconhecidas não interrompem o pipeline.
        return False

    @staticmethod
    def _get_decision_name(
        decision: Any,
    ) -> str:
        """
        Obtém o nome da decisão de maneira compatível
        com diferentes formatos de dataclass ou enum.
        """

        possible_attributes = (
            "decision",
            "decision_type",
            "type",
            "action",
            "strategy",
        )

        value: Any = decision

        for attribute in possible_attributes:
            candidate = getattr(
                decision,
                attribute,
                None,
            )

            if candidate is not None:
                value = candidate
                break

        enum_name = getattr(
            value,
            "name",
            None,
        )

        if isinstance(enum_name, str):
            return enum_name.upper().strip()

        enum_value = getattr(
            value,
            "value",
            None,
        )

        if isinstance(enum_value, str):
            return enum_value.upper().strip()

        text = str(value).strip().upper()

        if "." in text:
            text = text.rsplit(".", 1)[-1]

        return text

    @staticmethod
    def _get_decision_message(
        decision: Any,
    ) -> str:
        """
        Procura a pergunta ou mensagem criada pelo
        ReasoningEngine.
        """

        possible_attributes = (
            "question",
            "message",
            "response",
            "clarification",
            "reason",
        )

        for attribute in possible_attributes:
            value = getattr(
                decision,
                attribute,
                None,
            )

            if isinstance(value, str) and value.strip():
                return value.strip()

        return ""

    def _process_planner(
        self,
        command: str,
    ) -> bool:

        actions, results = self.controller.execute(command)

        if results:
            result_message = " ".join(
                str(result)
                for result in results
            )

            print(
                f"[AUTOMAÇÃO] {result_message}"
            )

            if actions:
                self.kernel.speech.say("Executando.")

                self._update_session_from_actions(
                    actions
                )
            else:
                self.kernel.speech.say(
                    result_message
                )

            self._add_turn(command, result_message)

            return True

        return False

    def _process_router(
        self,
        command: str,
    ) -> bool:
        result = self.kernel.router.route(command)

        if not result.handled:
            return False

        self.kernel.speech.say(
            result.message
        )

        self._add_turn(command, result.message)

        return True

    def _process_priority_router(
        self,
        command: str,
    ) -> bool:
        result = self.kernel.router.route_priority(command)

        if not result.handled:
            return False

        self.kernel.speech.say(result.message)
        self._add_turn(command, result.message)
        return True

    def _process_brain(
        self,
        command: str,
    ) -> None:
        memory_context = (
            self.kernel.memory.context(command)
        )

        conversation_context = (
            self.kernel.context.get_recent_history()
        )

        combined_context = self._combine_contexts(
            memory_context,
            conversation_context,
        )

        answer = self.kernel.brain.respond(
            command,
            combined_context,
        )

        self.kernel.speech.say(answer)

        self._add_turn(command, answer)

    def _add_turn(self, command: str, response: str) -> None:
        self.kernel.context.add_turn(command, response)
        auto_memory = getattr(self.kernel, "auto_memory", None)
        capture = getattr(auto_memory, "capture", None)

        if not callable(capture):
            return

        try:
            capture(command)
        except Exception:
            self.logger.exception(
                "Falha não bloqueante ao capturar memória automática"
            )

    def _announce_previous_session(self) -> None:
        session_data = self.kernel.session.load()

        if not session_data:
            return

        project = session_data.get("project")
        last_file = session_data.get("last_file")

        parts: list[str] = []

        if project:
            parts.append(
                f"Na última sessão você estava "
                f"trabalhando no projeto {project}."
            )

        if last_file:
            parts.append(
                f"O último arquivo aberto foi {last_file}."
            )

        if parts:
            self.kernel.speech.say(
                " ".join(parts)
            )

    def _update_session_from_actions(
        self,
        actions: list[Any],
    ) -> None:
        for action in actions:
            if action.type != "process.start":
                continue

            command = action.parameters.get(
                "command"
            )

            if isinstance(command, str):
                command_parts = [command]

            elif isinstance(command, (list, tuple)):
                command_parts = [
                    str(item)
                    for item in command
                ]

            else:
                continue

            for command_part in command_parts:
                normalized = command_part.lower()

                if "c:\\atlas2" in normalized:
                    self.kernel.session.save_project(
                        "Atlas2"
                    )

                if normalized.endswith(".py"):
                    filename = Path(
                        command_part
                    ).name

                    self.kernel.session.save_last_file(
                        filename
                    )

    def _prepare_command(
        self,
        spoken: str,
    ) -> str | None:
        if not self.kernel.wake_word_enabled:
            return spoken.strip()

        found, command = remove_wake_word(
            spoken,
            ATLAS_NAME,
        )

        if (
            self.kernel.router.pending_open
            or self.kernel.router.pending_system_action
        ):
            return spoken.lower().strip()

        if not found:
            print(
                f"[Aguardando a palavra '{ATLAS_NAME}']"
            )

            return None

        if not command:
            self.kernel.speech.say(
                "Pois não?"
            )

            followup = self.kernel.speech.listen(
                "Ouvindo seu comando..."
            )

            return (
                followup.strip()
                if followup
                else None
            )

        return command.strip()

    @staticmethod
    def _combine_contexts(
        memory_context: str,
        conversation_context: str,
    ) -> str:
        sections: list[str] = []

        if memory_context.strip():
            sections.append(
                "Memória permanente:\n"
                f"{memory_context.strip()}"
            )

        if conversation_context.strip():
            sections.append(
                "Conversa recente:\n"
                f"{conversation_context.strip()}"
            )

        return "\n\n".join(sections)
