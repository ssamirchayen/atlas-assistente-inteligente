"""Agente consultivo para criação, revisão e depuração de software."""

from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class ProgrammingAdvisorAgent:
    """Planeja assistência de código sem executar conteúdo recebido."""

    metadata = AgentMetadata(
        name="programming",
        display_name="Programming Advisor Agent",
        description=(
            "Apoia criação, revisão, depuração e segurança de software."
        ),
        domains=("programming", "code-review", "debugging", "security"),
        priority=282,
    )

    _MODES = (
        (
            "security",
            (
                "analise a seguranca",
                "analise de seguranca",
                "codigo inseguro",
                "falha de seguranca",
                "vulnerabilidade",
            ),
        ),
        (
            "debug",
            (
                "ache o bug",
                "achar o bug",
                "corrija o bug",
                "corrigir o bug",
                "depure",
                "debug",
                "erro no codigo",
                "encontre o bug",
                "por que esse codigo nao funciona",
            ),
        ),
        (
            "review",
            (
                "melhore este codigo",
                "melhorar codigo",
                "otimize o codigo",
                "refatore",
                "revisar codigo",
                "revise este codigo",
            ),
        ),
        (
            "create",
            (
                "codigo do zero",
                "crie codigo",
                "crie um codigo",
                "crie um sistema",
                "criar codigo",
                "criar um sistema",
                "desenvolva um programa",
                "faca um codigo",
                "implemente em",
                "programa do zero",
            ),
        ),
    )

    _LANGUAGES = {
        "c sharp": "C#",
        "c plus plus": "C++",
        "cplusplus": "C++",
        "cpp": "C++",
        "dart": "Dart",
        "go": "Go",
        "golang": "Go",
        "java": "Java",
        "javascript": "JavaScript",
        "kotlin": "Kotlin",
        "php": "PHP",
        "powershell": "PowerShell",
        "python": "Python",
        "ruby": "Ruby",
        "rust": "Rust",
        "sql": "SQL",
        "swift": "Swift",
        "typescript": "TypeScript",
    }

    _EXCLUDED_AUTOMATIONS = (
        "abra o arquivo",
        "abra o projeto",
        "execute o projeto",
        "inicie o atlas",
        "rode o projeto",
    )

    def plan(self, command: str) -> list[Action]:
        original = command.strip()

        if not original:
            return []

        normalized = self._normalize(original)

        if any(term in normalized for term in self._EXCLUDED_AUTOMATIONS):
            return []

        mode = self._identify_mode(normalized)

        if mode is None:
            return []

        return [
            Action(
                type="domain.programming_assist",
                parameters={
                    "mode": mode,
                    "language": self._identify_language(normalized),
                    "request": original,
                },
            )
        ]

    def _identify_mode(self, command: str) -> str | None:
        for mode, terms in self._MODES:
            if any(term in command for term in terms):
                return mode
        return None

    def _identify_language(self, command: str) -> str:
        padded = f" {command} "

        for alias, language in self._LANGUAGES.items():
            if f" {alias} " in padded:
                return language

        return "não informada"

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.casefold().strip())
        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )
        normalized = re.sub(r"[^\w\s+#]", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()
