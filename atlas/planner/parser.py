from __future__ import annotations

import re
import unicodedata


class CommandParser:
    """
    Divide um comando grande em vários comandos menores.

    Exemplo:

    "Abra o Google, espere 2 segundos e pesquise Atlas IA"

    Resultado:

    [
        "Abra o Google",
        "espere 2 segundos",
        "pesquise Atlas IA",
    ]
    """

    def parse(self, command: str) -> list[str]:
        command = command.strip()

        if not command:
            return []

        command = self._clean_command(command)

        parts = self._split_command(command)

        commands: list[str] = []

        for part in parts:
            cleaned_part = self._clean_part(part)

            if cleaned_part:
                commands.append(cleaned_part)

        if not commands:
            return [command]

        return commands

    @staticmethod
    def _clean_command(command: str) -> str:
        """
        Remove espaços repetidos e pontuação desnecessária.
        """

        command = re.sub(
            r"\s+",
            " ",
            command,
        )

        command = command.strip(
            " ,.;:"
        )

        return command

    def _split_command(
        self,
        command: str,
    ) -> list[str]:
        """
        Divide o texto usando conectores comuns da fala.
        """

        protected_command = self._protect_expressions(
            command
        )

        split_pattern = (
            r"\s*(?:"
            r",|;"
            r"|\bdepois\b"
            r"|\bem seguida\b"
            r"|\bna sequencia\b"
            r"|\bna sequência\b"
            r"|\be depois\b"
            r"|\bdepois disso\b"
            r"|\bpor fim\b"
            r"|\bfinalmente\b"
            r")\s*"
        )

        parts = re.split(
            split_pattern,
            protected_command,
            flags=re.IGNORECASE,
        )

        parts = [
            self._restore_expressions(part)
            for part in parts
        ]

        return self._split_using_and(parts)

    def _split_using_and(
        self,
        parts: list[str],
    ) -> list[str]:
        """
        Divide usando a palavra 'e' somente quando ela parece
        iniciar uma nova ação.
        """

        final_parts: list[str] = []

        action_words = (
            "abra",
            "abre",
            "abrir",
            "acesse",
            "acessar",
            "entre",
            "espere",
            "espera",
            "aguarde",
            "aguarda",
            "pesquise",
            "pesquisa",
            "buscar",
            "busque",
            "procure",
            "crie",
            "criar",
            "cria",
            "delete",
            "deletar",
            "exclua",
            "excluir",
            "apague",
            "apagar",
            "digite",
            "digitar",
            "escreva",
            "escrever",
            "pressione",
            "aperte",
            "tecle",
            "clique",
            "execute",
            "executar",
            "rode",
            "rodar",
            "feche",
            "fechar",
            "minimize",
            "minimizar",
            "maximize",
            "maximizar",
        )

        action_pattern = "|".join(
            re.escape(word)
            for word in action_words
        )

        pattern = (
            rf"\s+\be\b\s+"
            rf"(?=(?:{action_pattern})\b)"
        )

        for part in parts:
            subparts = re.split(
                pattern,
                part,
                flags=re.IGNORECASE,
            )

            final_parts.extend(subparts)

        return final_parts

    @staticmethod
    def _clean_part(part: str) -> str:
        """
        Limpa cada comando separado.
        """

        part = part.strip(
            " ,.;:"
        )

        part = re.sub(
            r"\s+",
            " ",
            part,
        )

        part = re.sub(
            r"^(?:entao|então)\s+",
            "",
            part,
            flags=re.IGNORECASE,
        )

        return part.strip()

    @staticmethod
    def _protect_expressions(command: str) -> str:
        """
        Protege expressões que possuem a palavra 'e',
        mas não representam duas ações.
        """

        replacements = {
            "copiar e colar": "copiar__E__colar",
            "arrastar e soltar": "arrastar__E__soltar",
            "salvar e fechar": "salvar__E__fechar",
            "login e senha": "login__E__senha",
            "nome e sobrenome": "nome__E__sobrenome",
        }

        protected = command

        for expression, replacement in replacements.items():
            protected = re.sub(
                re.escape(expression),
                replacement,
                protected,
                flags=re.IGNORECASE,
            )

        return protected

    @staticmethod
    def _restore_expressions(command: str) -> str:
        return command.replace(
            "__E__",
            " e ",
        )

    @staticmethod
    def normalize(text: str) -> str:
        """
        Normaliza texto para futuras comparações.
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