from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class HelpDeskAgent:
    """Classifica incidentes comuns e solicita uma triagem de TI."""

    metadata = AgentMetadata(
        name="helpdesk",
        display_name="IT Help Desk Agent",
        description="Planeja diagnósticos seguros para incidentes comuns de TI.",
        domains=("helpdesk", "it-support", "diagnostics", "infrastructure"),
        priority=275,
    )

    _SEARCH_PREFIXES = (
        "busque ",
        "pesquise ",
        "procure ",
    )
    _SUPPORT_SIGNALS = (
        "como resolver",
        "diagnostico",
        "diagnostique",
        "erro",
        "falha",
        "help desk",
        "lento",
        "me ajude",
        "nao abre",
        "nao conecta",
        "nao funciona",
        "nao imprime",
        "offline",
        "parou de funcionar",
        "problema",
        "sem internet",
        "sem som",
        "suporte tecnico",
        "travando",
    )

    def plan(self, command: str) -> list[Action]:
        original = command.strip()

        if not original:
            return []

        normalized = self._normalize(original)

        if normalized.startswith(self._SEARCH_PREFIXES):
            return []

        if not any(signal in normalized for signal in self._SUPPORT_SIGNALS):
            return []

        category = self._classify(normalized)

        if category is None:
            return []

        return [
            Action(
                type="helpdesk.diagnose",
                parameters={
                    "category": category,
                    "problem": original,
                },
            )
        ]

    @staticmethod
    def _classify(command: str) -> str | None:
        categories = (
            (
                "network",
                (
                    "internet",
                    "rede",
                    "wi fi",
                    "wifi",
                    "conexao",
                    "cabo de rede",
                ),
            ),
            (
                "printer",
                ("impressora", "imprimir", "impressao", "spooler"),
            ),
            (
                "audio",
                ("audio", "microfone", "som", "alto falante", "fone"),
            ),
            (
                "performance",
                (
                    "computador lento",
                    "pc lento",
                    "notebook lento",
                    "travando",
                    "desempenho",
                ),
            ),
            (
                "application",
                ("aplicativo", "programa", "software", "sistema"),
            ),
            (
                "general",
                ("help desk", "suporte tecnico", "problema de ti"),
            ),
        )

        for category, terms in categories:
            if any(term in command for term in terms):
                return category

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.casefold().strip())
        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()
