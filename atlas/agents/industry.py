"""Agente consultivo para operações industriais de Manaus."""

from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class IndustrialOperationsAgent:
    """Apoia a análise sem controlar máquinas ou remover proteções."""

    metadata = AgentMetadata(
        name="industry",
        display_name="Manaus Industrial Operations Agent",
        description=(
            "Apoia produção, qualidade e manutenção no ambiente industrial."
        ),
        domains=("industry", "manufacturing", "maintenance", "quality"),
        priority=292,
    )

    _SIGNALS = (
        "chao de fabrica",
        "industria",
        "industrial",
        "linha de producao",
        "manutencao preditiva",
        "manutencao preventiva",
        "oee",
        "polo industrial de manaus",
        "processo produtivo",
    )

    def plan(self, command: str) -> list[Action]:
        original = command.strip()

        if not original:
            return []

        normalized = self._normalize(original)

        if not any(signal in normalized for signal in self._SIGNALS):
            return []

        return [
            Action(
                type="domain.industry_analysis",
                parameters={
                    "mode": self._identify_mode(normalized),
                    "request": original,
                    "machine_control": False,
                },
            )
        ]

    @staticmethod
    def _identify_mode(command: str) -> str:
        categories = (
            (
                "safety",
                ("acidente", "nr 12", "protecao", "risco", "seguranca"),
            ),
            (
                "maintenance",
                ("falha", "manutencao", "parada", "preditiva", "preventiva"),
            ),
            ("quality", ("defeito", "inspecao", "qualidade", "retrabalho")),
            ("production", ("capacidade", "linha", "oee", "producao")),
        )

        for mode, terms in categories:
            if any(term in command for term in terms):
                return mode

        return "operations"

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
