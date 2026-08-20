"""Agente consultivo para comércio atacadista."""

from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class WholesaleAgent:
    """Planeja análises sem alterar preço, estoque ou pedido."""

    metadata = AgentMetadata(
        name="wholesale",
        display_name="Wholesale Operations Agent",
        description="Apoia estoque, margem, demanda e logística atacadista.",
        domains=("wholesale", "inventory", "pricing", "logistics"),
        priority=288,
    )

    _SIGNALS = (
        "atacado",
        "atacadista",
        "centro de distribuicao",
        "curva abc",
        "distribuidor",
        "giro de estoque",
        "margem de produto",
        "ruptura de estoque",
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
                type="domain.wholesale_analysis",
                parameters={
                    "mode": self._identify_mode(normalized),
                    "request": original,
                },
            )
        ]

    @staticmethod
    def _identify_mode(command: str) -> str:
        categories = (
            ("inventory", ("estoque", "ruptura", "curva abc", "giro")),
            ("pricing", ("margem", "preco", "rentabilidade")),
            ("demand", ("demanda", "previsao", "sazonalidade")),
            ("logistics", ("distribuicao", "entrega", "rota", "logistica")),
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
