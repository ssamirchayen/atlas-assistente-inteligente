from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class SalesAgent:
    """Planeja solicitações comerciais simples e determinísticas."""

    metadata = AgentMetadata(
        name="sales",
        display_name="Sales Agent",
        description=(
            "Cria abordagens comerciais e mensagens de acompanhamento."
        ),
        domains=("sales", "commercial", "customer-service", "leads"),
        priority=250,
    )

    _APPROACH_TERMS = (
        "abordagem comercial",
        "abordagem de venda",
        "abordagem de renda",
        "mensagem comercial",
        "mensagem de venda",
        "mensagem de vendas",
        "mensagem de renda",
        "script comercial",
        "script de venda",
        "script de renda",
        "texto comercial",
        "texto de venda",
        "texto de renda",
    )
    _FOLLOW_UP_TERMS = (
        "follow up",
        "followup",
        "mensagem de retorno",
        "retomar contato",
        "retorno comercial",
    )

    def plan(self, command: str) -> list[Action]:
        original = command.strip()

        if not original:
            return []

        normalized = self._normalize(original)
        style = self._identify_style(normalized)

        if style is None:
            return []

        return [
            Action(
                type="sales.compose_message",
                parameters={
                    "style": style,
                    "offering": self._extract_offering(original),
                },
            )
        ]

    def _identify_style(self, command: str) -> str | None:
        if any(term in command for term in self._FOLLOW_UP_TERMS):
            return "follow_up"

        if any(term in command for term in self._APPROACH_TERMS):
            return "approach"

        message_terms = ("abordagem", "mensagem", "script", "texto")
        sales_terms = (
            "comercial",
            "venda",
            "vendas",
            "vender",
            "renda",
        )

        if (
            any(term in command for term in message_terms)
            and any(term in command for term in sales_terms)
        ):
            return "approach"

        return None

    @classmethod
    def _extract_offering(cls, command: str) -> str:
        clean_command = command.strip().rstrip(" .?!")
        patterns = (
            r"interessad[oa]\s+(?:no|na|em)\s+(.+)$",
            r"(?:vender|oferecer|divulgar)\s+(?:uma|um|o|a)?\s*(.+)$",
            r"(?:para|sobre)\s+(?:uma|um|o|a)?\s*(.+)$",
        )

        for pattern in patterns:
            match = re.search(pattern, clean_command, flags=re.IGNORECASE)

            if match:
                offering = match.group(1).strip().rstrip(" .?!")

                if offering:
                    return offering

        return "nosso produto ou serviço"

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
