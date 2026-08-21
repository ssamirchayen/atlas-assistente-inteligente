from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass
class Intent:
    name: str
    confidence: float


class IntentAnalyzer:

    def analyze(self, command: str) -> Intent:
        command = self._normalize(command)

        # Conversas e perguntas informativas nunca devem virar automação
        # apenas porque citam um programa, arquivo ou recurso do sistema.
        if self._is_conversational_request(command):
            return Intent(
                "chat",
                0.99,
            )

        if self._contains(
            command,
            "continue",
            "continuar",
            "onde paramos",
            "retome",
            "retomar",
        ):
            return Intent(
                "resume_session",
                0.99,
            )

        if self._contains(
            command,
            "arquivo",
            ".py",
            "planner",
            "engine",
            "kernel",
            "desktop",
            "speech",
            "manager",
        ):
            return Intent(
                "open_file",
                0.98,
            )

        if self._contains(
            command,
            "vs code",
            "vscode",
            "chrome",
            "calculadora",
            "paint",
            "terminal",
            "powershell",
            "bloco de notas",
        ):
            return Intent(
                "open_program",
                0.95,
            )

        if self._contains(
            command,
            "execute o projeto",
            "rodar projeto",
            "execute atlas",
            "rodar atlas",
        ):
            return Intent(
                "run_project",
                0.95,
            )

        return Intent(
            "chat",
            0.50,
        )

    def _is_conversational_request(
        self,
        command: str,
    ) -> bool:
        conversational_prefixes = (
            "me explique",
            "explique",
            "como funciona",
            "como funcionam",
            "como posso",
            "como eu posso",
            "como fazer",
            "como abrir",
            "o que e",
            "o que sao",
            "qual e",
            "qual a",
            "qual o",
            "quais sao",
            "por que",
            "porque",
            "me diga",
            "fale sobre",
            "conte sobre",
            "de exemplos",
            "de alguns exemplos",
        )

        return command.startswith(conversational_prefixes)

    def _contains(
        self,
        command: str,
        *words: str,
    ) -> bool:
        return any(
            word in command
            for word in words
        )

    @staticmethod
    def _normalize(
        text: str,
    ) -> str:

        text = text.lower()

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            c
            for c in text
            if not unicodedata.combining(c)
        )

        text = re.sub(
            r"[^\w\s.]",
            " ",
            text,
        )

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()