from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class BrowserAgent:
    """
    Interpreta comandos relacionados ao navegador e os transforma
    em ações executáveis pelo AutomationEngine.
    """

    metadata = AgentMetadata(
        name="browser",
        display_name="Browser Agent",
        description="Planeja navegação e interação com páginas web.",
        domains=("browser", "web", "research"),
        priority=300,
    )

    def plan(self, command: str) -> list[Action]:
        original_command = command.strip()

        if not original_command:
            return []

        normalized_command = self._normalize(original_command)
        normalized_command = self._correct_voice_variations(
            normalized_command
        )

        # ==================================================
        # CLICAR EM RESULTADOS DE PESQUISA
        # ==================================================

        first_result_match = re.match(
            (
                r"^(?:clique|abra|entre)"
                r"\s+(?:no|na|o|a)?\s*"
                r"(?:primeiro|1|1o|primeira)"
                r"\s+resultado"
                r"(?:\s+da\s+(?:pesquisa|busca)"
                r"\s+(?:anterior|passada|ultima))?$"
            ),
            normalized_command,
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
                r"\s+(?:no|na|o|a)?\s*"
                r"(?:segundo|2|2o|segunda)"
                r"\s+resultado"
                r"(?:\s+da\s+(?:pesquisa|busca)"
                r"\s+(?:anterior|passada|ultima))?$"
            ),
            normalized_command,
        )

        if second_result_match:
            return [
                Action(
                    type="browser.click_second_result",
                    parameters={},
                )
            ]

        # ==================================================
        # PRESSIONAR TECLA NO NAVEGADOR
        # ==================================================

        press_key_match = re.match(
            (
                r"^(?:pressione|aperte|tecle)"
                r"\s+(?:a\s+tecla\s+)?"
                r"(.+)$"
            ),
            normalized_command,
        )

        if press_key_match:
            key = press_key_match.group(1).strip()

            key_aliases = {
                "entrada": "enter",
                "enter": "enter",
                "retorno": "enter",
                "espaco": "space",
                "barra de espaco": "space",
                "escape": "esc",
                "esc": "esc",
                "tab": "tab",
                "tabulacao": "tab",
                "backspace": "backspace",
                "apagar": "backspace",
                "delete": "delete",
                "deletar": "delete",
                "seta para cima": "arrowup",
                "seta acima": "arrowup",
                "seta para baixo": "arrowdown",
                "seta abaixo": "arrowdown",
                "seta para esquerda": "arrowleft",
                "seta para a esquerda": "arrowleft",
                "seta para direita": "arrowright",
                "seta para a direita": "arrowright",
                "home": "home",
                "inicio": "home",
                "end": "end",
                "fim": "end",
                "page up": "pageup",
                "pagina acima": "pageup",
                "page down": "pagedown",
                "pagina abaixo": "pagedown",
            }

            key = key_aliases.get(key, key)

            return [
                Action(
                    type="browser.press_key",
                    parameters={
                        "key": key,
                    },
                )
            ]

        # ==================================================
        # PREENCHER CAMPO
        # ==================================================

        fill_input_match = re.match(
            (
                r"^(?:preencha|preencher|coloque|insira)"
                r"\s+(?:o\s+campo\s+|no\s+campo\s+|"
                r"na\s+caixa\s+|a\s+caixa\s+)?"
                r"(.+?)"
                r"\s+(?:com|usando|colocando)"
                r"\s+(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if fill_input_match:
            field = fill_input_match.group(1).strip()
            value = fill_input_match.group(2).strip()

            if field and value:
                return [
                    Action(
                        type="browser.fill_input",
                        parameters={
                            "field": field,
                            "value": value,
                        },
                    )
                ]

        # Também aceita:
        # "digite Manaus no campo cidade"
        type_in_field_match = re.match(
            (
                r"^(?:digite|escreva|coloque)"
                r"\s+(.+?)"
                r"\s+(?:no|na|em)"
                r"\s+(?:campo|caixa|entrada)"
                r"\s+(.+)$"
            ),
            original_command,
            flags=re.IGNORECASE,
        )

        if type_in_field_match:
            value = type_in_field_match.group(1).strip()
            field = type_in_field_match.group(2).strip()

            if field and value:
                return [
                    Action(
                        type="browser.fill_input",
                        parameters={
                            "field": field,
                            "value": value,
                        },
                    )
                ]

        # ==================================================
        # CLICAR EM TEXTO OU BOTÃO
        # ==================================================

        click_text_match = re.match(
            (
                r"^(?:clique|clicar|selecione|selecionar)"
                r"\s+(?:em|no|na|nos|nas|o|a)?\s*"
                r"(.+)$"
            ),
            normalized_command,
        )

        if click_text_match:
            text = click_text_match.group(1).strip()

            # Evita transformar frases incompletas em cliques.
            invalid_targets = {
                "",
                "aqui",
                "ali",
                "la",
                "isso",
                "aquilo",
            }

            if text not in invalid_targets:
                return [
                    Action(
                        type="browser.click_text",
                        parameters={
                            "text": text,
                        },
                    )
                ]

        # ==================================================
        # ESPERAR CARREGAMENTO DA PÁGINA
        # ==================================================

        wait_match = re.match(
            (
                r"^(?:espere|espera|aguarde|aguarda)"
                r"\s+(\d+(?:[.,]\d+)?)"
                r"\s*(?:segundo|segundos|s)?"
                r"(?:\s+na\s+pagina)?$"
            ),
            normalized_command,
        )

        if wait_match:
            seconds_text = wait_match.group(1).replace(",", ".")
            seconds = float(seconds_text)

            return [
                Action(
                    type="browser.wait_page",
                    parameters={
                        "seconds": seconds,
                    },
                )
            ]

        # ==================================================
        # FECHAR NAVEGADOR
        # ==================================================

        if normalized_command in {
            "feche o navegador",
            "fecha o navegador",
            "fechar navegador",
            "feche o browser",
            "fecha o browser",
            "encerre o navegador",
            "encerra o navegador",
        }:
            return [
                Action(
                    type="browser.close",
                    parameters={},
                )
            ]

        # ==================================================
        # INFORMAR URL ATUAL
        # ==================================================

        if normalized_command in {
            "qual e a url atual",
            "qual a url atual",
            "qual o endereco atual",
            "mostre a url atual",
            "mostra a url atual",
            "me diga a url atual",
            "diga a url atual",
        }:
            return [
                Action(
                    type="browser.current_url",
                    parameters={},
                )
            ]

        # ==================================================
        # INFORMAR TÍTULO DA PÁGINA
        # ==================================================

        if normalized_command in {
            "qual e o titulo da pagina",
            "qual o titulo da pagina",
            "mostre o titulo da pagina",
            "mostra o titulo da pagina",
            "me diga o titulo da pagina",
            "diga o titulo da pagina",
        }:
            return [
                Action(
                    type="browser.page_title",
                    parameters={},
                )
            ]

        return []

    @staticmethod
    def _correct_voice_variations(text: str) -> str:
        """
        Corrige variações e pequenos erros comuns do reconhecimento de voz.
        """

        replacements = {
            "click ": "clique ",
            "clicka ": "clique ",
            "clickar ": "clique ",
            "clica ": "clique ",
            "clic ": "clique ",
            "clicar ": "clique ",
            "cliquei ": "clique ",
            "seleciona ": "selecione ",
            "selecionar ": "selecione ",
            "aperta ": "aperte ",
            "apertar ": "aperte ",
            "precione ": "pressione ",
            "presione ": "pressione ",
            "pressionar ": "pressione ",
            "aguardar ": "aguarde ",
            "esperar ": "espere ",
            "fecha ": "feche ",
            "fechar ": "feche ",
        }

        for variation, correction in replacements.items():
            if text.startswith(variation):
                remainder = text[len(variation):]
                return correction + remainder

        return text

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Coloca o texto em letras minúsculas, remove acentos,
        pontuação desnecessária e espaços duplicados.
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
            r"[?!.,;:]",
            "",
            normalized,
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        return normalized.strip()
