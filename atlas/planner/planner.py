from __future__ import annotations

import re
import unicodedata

from atlas.agents.browser import BrowserAgent
from atlas.agents.coding import CodingAgent
from atlas.agents.desktop import DesktopAgent
from atlas.agents.helpdesk import HelpDeskAgent
from atlas.agents.registry import AgentRegistry
from atlas.agents.sales import SalesAgent
from atlas.context.manager import ContextManager
from atlas.intent.analyzer import IntentAnalyzer
from atlas.planner.actions import Action
from atlas.planner.intelligent import IntelligentPlanner
from atlas.planner.parser import CommandParser


class Planner:
    def __init__(self, context: ContextManager) -> None:
        self.context = context
        self.session = context.session
        self.desktop_agent = DesktopAgent()
        self.coding_agent = CodingAgent()
        self.helpdesk_agent = HelpDeskAgent()
        self.sales_agent = SalesAgent()
        self.browser_agent = BrowserAgent()
        self.agent_registry = AgentRegistry(
            (
                self.browser_agent,
                self.helpdesk_agent,
                self.sales_agent,
                self.coding_agent,
                self.desktop_agent,
            )
        )
        self.intent_analyzer = IntentAnalyzer()
        self.intelligent = IntelligentPlanner(context)
        self.command_parser = CommandParser()

    def plan(self, command: str) -> list[Action]:
        original_command = command.strip()

        if not original_command:
            return []

        # Registra automaticamente o último comando recebido.
        self.session.save_last_command(original_command)

        parsed_commands = self.command_parser.parse(original_command)

        if len(parsed_commands) > 1:
            print(
                f"[PARSER] {len(parsed_commands)} comandos encontrados."
            )

            actions: list[Action] = []

            for parsed_command in parsed_commands:
                print(f"[PARSER] Analisando: {parsed_command}")

                command_actions = self._plan_single_command(
                    parsed_command,
                    show_logs=False,
                )

                if command_actions:
                    actions.extend(command_actions)
                else:
                    print(
                        "[PARSER] Nenhuma ação criada para: "
                        f"{parsed_command}"
                    )

            if actions:
                print("[PLANNER] Plano composto criado pelo parser.")

                for action in actions:
                    print(f"[PLANO] {action}")

                return actions

        return self._plan_single_command(original_command)

    def _plan_single_command(
        self,
        command: str,
        *,
        show_logs: bool = True,
    ) -> list[Action]:
        original_command = command.strip()

        if not original_command:
            return []

        normalized_command = self._normalize(original_command)

        # 1. Comandos compostos já conhecidos.
        combined_actions = self._plan_combined_commands(
            original_command,
            normalized_command,
        )

        if combined_actions:
            if show_logs:
                print("[PLANNER] Comando composto reconhecido.")

                for action in combined_actions:
                    print(f"[PLANO] {action}")

            return combined_actions

        # 2. Comandos diretos e rápidos.
        direct_actions = self._plan_direct_automation(
            original_command,
            normalized_command,
        )

        if direct_actions:
            if show_logs:
                print("[PLANNER] Automação direta reconhecida.")

                for action in direct_actions:
                    print(f"[PLANO] {action}")

            return direct_actions

        # 3. Agente especializado em suporte de TI.
        helpdesk_selection = self.agent_registry.route(
            original_command,
            candidates=("helpdesk",),
        )

        if helpdesk_selection is not None:
            if show_logs:
                print(
                    "[PLANNER] "
                    f"{helpdesk_selection.metadata.display_name} "
                    "reconheceu o incidente."
                )

                for action in helpdesk_selection.actions:
                    print(f"[PLANO] {action}")

            return list(helpdesk_selection.actions)

        # 4. Agente especializado em vendas.
        sales_selection = self.agent_registry.route(
            original_command,
            candidates=("sales",),
        )

        if sales_selection is not None:
            if show_logs:
                print(
                    "[PLANNER] "
                    f"{sales_selection.metadata.display_name} "
                    "reconheceu o comando."
                )

                for action in sales_selection.actions:
                    print(f"[PLANO] {action}")

            return list(sales_selection.actions)

        # 5. Agente especializado em navegação.
        browser_selection = self.agent_registry.route(
            original_command,
            candidates=("browser",),
        )

        if browser_selection is not None:
            if show_logs:
                print(
                    "[PLANNER] "
                    f"{browser_selection.metadata.display_name} "
                    "reconheceu o comando."
                )

                for action in browser_selection.actions:
                    print(f"[PLANO] {action}")

            return list(browser_selection.actions)

        # 6. Análise tradicional de intenção.
        intent = self.intent_analyzer.analyze(original_command)

        if show_logs:
            print(
                f"[INTENT] {intent.name} "
                f"({intent.confidence:.2f})"
            )

        # Tarefas relacionadas à programação.
        if intent.name in {
            "resume_session",
            "open_file",
            "run_project",
        }:
            coding_selection = self.agent_registry.route(
                original_command,
                candidates=("coding",),
            )

            if coding_selection is not None:
                return list(coding_selection.actions)

        # Tarefas relacionadas ao Windows.
        if intent.name == "open_program":
            desktop_selection = self.agent_registry.route(
                original_command,
                candidates=("desktop",),
            )

            if desktop_selection is not None:
                return list(desktop_selection.actions)

        # 7. Fallback dos agentes tradicionais.
        agent_selection = self.agent_registry.route(
            original_command,
            candidates=("coding", "desktop"),
        )

        if agent_selection is not None:
            if show_logs:
                print(
                    "[PLANNER] "
                    f"{agent_selection.metadata.display_name} "
                    "reconheceu o comando."
                )

            return list(agent_selection.actions)

        # 8. Planner Inteligente.
        intelligent_actions = self.intelligent.plan(
            original_command
        )

        if intelligent_actions:
            if show_logs:
                print("[PLANNER] Plano criado pela IA.")

                for action in intelligent_actions:
                    print(f"[PLANO IA] {action}")

            return intelligent_actions

        if show_logs:
            print("[PLANNER] Nenhuma ação foi criada.")

        return []

    def get_session_context(self) -> str:
        """Retorna o contexto atual da sessão para outros módulos."""
        return self.session.build_prompt_context()

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Coloca o texto em letras minúsculas,
        remove acentos e espaços duplicados.
        """

        normalized = unicodedata.normalize(
            "NFKD",
            text.lower().strip(),
        )

        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        return normalized.strip()

    @staticmethod
    def _normalize_spoken_filename(filename: str) -> str:
        """
        Converte extensões faladas para o formato correto.

        Exemplos:
        ideias ponto txt -> ideias.txt
        arquivo ponto py -> arquivo.py
        pagina ponto html -> pagina.html
        """

        filename = filename.strip()

        filename = re.sub(
            r"\s+ponto\s+",
            ".",
            filename,
            flags=re.IGNORECASE,
        )

        filename = re.sub(
            r"\s+dot\s+",
            ".",
            filename,
            flags=re.IGNORECASE,
        )

        filename = re.sub(
            r"\s+",
            " ",
            filename,
        )

        return filename.strip()

    def _plan_combined_commands(
        self,
        original_command: str,
        normalized_command: str,
    ) -> list[Action]:
        """
        Planeja comandos com mais de uma ação.
        """

        # ==================================================
        # CRIAR PASTA E ARQUIVO DENTRO DELA
        # ==================================================

        folder_and_file_match = re.match(
            (
                r"^(?:crie|criar|cria|faca|faça)\s+"
                r"(?:uma\s+)?pasta"
                r"(?:\s+chamada|\s+com\s+o\s+nome)?"
                r"\s+(.+?)"
                r"\s+e\s+(?:dentro\s+dela\s+)?"
                r"(?:crie|criar|cria|faca|faça)\s+"
                r"(?:um\s+)?arquivo"
                r"(?:\s+chamado|\s+com\s+o\s+nome)?"
                r"\s+(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if folder_and_file_match:
            folder_name = folder_and_file_match.group(1).strip()
            file_name = folder_and_file_match.group(2).strip()

            file_name = self._normalize_spoken_filename(
                file_name
            )

            if folder_name and file_name:
                return [
                    Action(
                        type="file.create_folder",
                        parameters={
                            "path": folder_name,
                        },
                    ),
                    Action(
                        type="file.create_file",
                        parameters={
                            "path": f"{folder_name}/{file_name}",
                        },
                    ),
                ]

        # ==================================================
        # ABRIR YOUTUBE E PESQUISAR
        # ==================================================

        youtube_match = re.match(
            (
                r"^(?:abra|abre|abrir)\s+"
                r"(?:o\s+)?youtube"
                r"\s+e\s+"
                r"(?:pesquise|pesquisa|buscar|busque|procure)"
                r"(?:\s+por)?\s+(.+)$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if youtube_match:
            query = youtube_match.group(1).strip()

            if query:
                return [
                    Action(
                        type="browser.youtube_search",
                        parameters={
                            "query": query,
                        },
                    )
                ]

        # ==================================================
        # ABRIR GOOGLE E PESQUISAR
        # ==================================================

        google_match = re.match(
            (
                r"^(?:abra|abre|abrir)\s+"
                r"(?:o\s+)?google"
                r"\s+e\s+"
                r"(?:pesquise|pesquisa|buscar|busque|procure)"
                r"(?:\s+por)?\s+(.+)$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if google_match:
            query = google_match.group(1).strip()

            if query:
                return [
                    Action(
                        type="browser.search",
                        parameters={
                            "query": query,
                        },
                    )
                ]

        # ==================================================
        # ABRIR BLOCO DE NOTAS E ESCREVER
        # ==================================================

        notepad_match = re.match(
            (
                r"^(?:abra|abre|abrir)\s+"
                r"(?:o\s+)?bloco\s+de\s+notas"
                r"\s+e\s+"
                r"(?:digite|escreva|digitar|escrever)"
                r"\s+(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if notepad_match:
            text = notepad_match.group(1).strip()

            if text:
                return [
                    Action(
                        type="process.start",
                        parameters={
                            "command": ["notepad.exe"],
                        },
                    ),
                    Action(
                        type="system.wait",
                        parameters={
                            "seconds": 1.5,
                        },
                    ),
                    Action(
                        type="keyboard.write",
                        parameters={
                            "text": text,
                        },
                    ),
                ]

        return []

    def _plan_direct_automation(
        self,
        original_command: str,
        normalized_command: str,
    ) -> list[Action]:
        """
        Planeja comandos simples usando regras rápidas.
        """

        # ==================================================
        # ARQUIVOS E PASTAS
        # ==================================================

        # Criar pasta.
        create_folder_match = re.match(
            (
                r"^(?:crie|criar|cria|faca|faça)\s+"
                r"(?:uma\s+)?pasta"
                r"(?:\s+chamada|\s+com\s+o\s+nome)?"
                r"\s+(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if create_folder_match:
            folder_name = create_folder_match.group(1).strip()

            if folder_name:
                return [
                    Action(
                        type="file.create_folder",
                        parameters={
                            "path": folder_name,
                        },
                    )
                ]

        # Criar arquivo.
        create_file_match = re.match(
            (
                r"^(?:crie|criar|cria|faca|faça)\s+"
                r"(?:um\s+)?arquivo"
                r"(?:\s+chamado|\s+com\s+o\s+nome)?"
                r"\s+(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if create_file_match:
            file_name = create_file_match.group(1).strip()

            file_name = self._normalize_spoken_filename(
                file_name
            )

            if file_name:
                return [
                    Action(
                        type="file.create_file",
                        parameters={
                            "path": file_name,
                        },
                    )
                ]

        # Excluir arquivo ou pasta.
        delete_match = re.match(
            (
                r"^(?:exclua|excluir|delete|deletar|apague|apagar)"
                r"\s+(?:o\s+|a\s+)?"
                r"(?:arquivo\s+|pasta\s+)?"
                r"(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if delete_match:
            target = delete_match.group(1).strip()

            target = self._normalize_spoken_filename(
                target
            )

            if target:
                return [
                    Action(
                        type="file.delete",
                        parameters={
                            "path": target,
                        },
                    )
                ]

        # ==================================================
        # NAVEGADOR
        # ==================================================

        # Abrir site conhecido.
        open_site_match = re.match(
            (
                r"^(?:abra|abre|abrir|acesse|acessar|entre\s+no)"
                r"\s+(?:o\s+|a\s+)?"
                r"(github|youtube|google|gmail|facebook|"
                r"instagram|linkedin|whatsapp)$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if open_site_match:
            site_name = open_site_match.group(1).strip()

            return [
                Action(
                    type="browser.open_site",
                    parameters={
                        "name": site_name,
                    },
                )
            ]

        # Pesquisar no YouTube.
        youtube_search_match = re.match(
            (
                r"^(?:pesquise|pesquisa|buscar|busque|procure)"
                r"(?:\s+no|\s+na)?\s+youtube"
                r"(?:\s+por)?\s+(.+)$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if youtube_search_match:
            query = youtube_search_match.group(1).strip()

            if query:
                return [
                    Action(
                        type="browser.youtube_search",
                        parameters={
                            "query": query,
                        },
                    )
                ]

        # Pesquisar no Google.
        google_search_match = re.match(
            (
                r"^(?:pesquise|pesquisa|buscar|busque|procure)"
                r"(?:\s+no|\s+na)?\s+google"
                r"(?:\s+por)?\s+(.+)$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if google_search_match:
            query = google_search_match.group(1).strip()

            if query:
                return [
                    Action(
                        type="browser.search",
                        parameters={
                            "query": query,
                        },
                    )
                ]

        # Pesquisa genérica.
        generic_search_match = re.match(
            (
                r"^(?:pesquise|pesquisa|buscar|busque|procure)"
                r"(?:\s+por)?\s+(.+)$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if generic_search_match:
            query = generic_search_match.group(1).strip()

            if query:
                return [
                    Action(
                        type="browser.search",
                        parameters={
                            "query": query,
                        },
                    )
                ]

        # Abrir somente o navegador.
        if normalized_command in {
            "abra o navegador",
            "abre o navegador",
            "abrir navegador",
            "abra o browser",
            "abra a internet",
        }:
            return [
                Action(
                    type="browser.open",
                    parameters={},
                )
            ]

        # ==================================================
        # TECLADO
        # ==================================================

        typing_match = re.match(
            (
                r"^(?:digite|escreva|digitar|escrever)"
                r"\s+(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if typing_match:
            text = typing_match.group(1).strip()

            if text:
                return [
                    Action(
                        type="keyboard.write",
                        parameters={
                            "text": text,
                        },
                    )
                ]

        key_match = re.match(
            (
                r"^(?:pressione|aperte|tecle)"
                r"\s+(.+)$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if key_match:
            key = key_match.group(1).strip()

            key_aliases = {
                "entrada": "enter",
                "enter": "enter",
                "espaco": "space",
                "barra de espaco": "space",
                "escape": "esc",
                "esc": "esc",
                "tab": "tab",
                "tabulacao": "tab",
                "backspace": "backspace",
                "apagar": "backspace",
            }

            key = key_aliases.get(key, key)

            if key:
                return [
                    Action(
                        type="keyboard.press",
                        parameters={
                            "key": key,
                        },
                    )
                ]

        # ==================================================
        # SISTEMA
        # ==================================================

        wait_match = re.match(
            (
                r"^(?:espere|espera|aguarde|aguarda)"
                r"\s+(\d+(?:[.,]\d+)?)"
                r"\s*(?:segundo|segundos|s)?$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if wait_match:
            seconds_text = wait_match.group(1).replace(",", ".")
            seconds = float(seconds_text)

            return [
                Action(
                    type="system.wait",
                    parameters={
                        "seconds": seconds,
                    },
                )
            ]

        # ==================================================
        # CLIQUES ESPECÍFICOS
        # ==================================================

        first_result_match = re.match(
            (
                r"^(?:clique|abra|entre)"
                r"\s+(?:no|na)?\s*"
                r"(?:primeiro|1(?:º|o)?|primeira)"
                r"\s+resultado"
                r"(?:\s+da\s+(?:pesquisa|busca)"
                r"\s+(?:anterior|passada|ultima))?$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if first_result_match:
            return [
                Action(
                    type="browser.click_first_result",
                    parameters={},
                )
            ]

        second_result_match = re.match(
            (
                r"^(?:clique|abra|entre)"
                r"\s+(?:no|na)?\s*"
                r"(?:segundo|2(?:º|o)?|segunda)"
                r"\s+resultado"
                r"(?:\s+da\s+(?:pesquisa|busca)"
                r"\s+(?:anterior|passada|ultima))?$"
            ),
            normalized_command,
            flags=re.IGNORECASE,
        )

        if second_result_match:
            return [
                Action(
                    type="browser.click_second_result",
                    parameters={},
                )
            ]

        # ==================================================
        # MOUSE
        # ==================================================

        if normalized_command in {
            "clique",
            "de um clique",
            "clique aqui",
            "clique com o mouse",
        }:
            return [
                Action(
                    type="mouse.click",
                    parameters={},
                )
            ]

        return []
