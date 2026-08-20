"""Agente de apoio radiológico com revisão humana obrigatória."""

from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class RadiologySupportAgent:
    """Organiza apoio ao exame sem emitir diagnóstico ou laudo."""

    metadata = AgentMetadata(
        name="radiology",
        display_name="Radiology Support Agent",
        description=(
            "Apoia qualidade e fluxo radiológico sob revisão profissional."
        ),
        domains=("radiology", "medical-imaging", "health-support"),
        priority=295,
    )

    _RADIOLOGY_TERMS = (
        "imagem medica",
        "laudo radiologico",
        "radiografia",
        "radiologia",
        "raio x",
        "raios x",
    )
    _PROGRAMMING_CONTEXT = (
        "aplicativo",
        "codigo",
        "programa",
        "sistema para",
        "software",
    )

    def plan(self, command: str) -> list[Action]:
        original = command.strip()

        if not original:
            return []

        normalized = self._normalize(original)

        if not any(term in normalized for term in self._RADIOLOGY_TERMS):
            return []
        if any(term in normalized for term in self._PROGRAMMING_CONTEXT):
            return []

        return [
            Action(
                type="domain.radiology_support",
                parameters={
                    "mode": self._identify_mode(normalized),
                    "request": original,
                    "human_review_required": True,
                },
            )
        ]

    @staticmethod
    def _identify_mode(command: str) -> str:
        if any(
            term in command
            for term in ("qualidade", "contraste", "posicionamento")
        ):
            return "quality_check"
        if any(
            term in command
            for term in ("fila", "organize", "priorize", "worklist")
        ):
            return "worklist"
        return "clinical_support"

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
