from __future__ import annotations

from typing import Any


class SalesAutomation:
    """Produz mensagens comerciais a partir de planos do Sales Agent."""

    def compose_message(self, parameters: dict[str, Any]) -> str:
        style = str(parameters.get("style", "")).strip().casefold()
        offering = str(
            parameters.get("offering", "nosso produto ou serviço")
        ).strip()

        if not offering:
            offering = "nosso produto ou serviço"

        if style == "approach":
            return (
                "Olá! Tudo bem?\n\n"
                f"Quero te apresentar {offering}, uma oportunidade para "
                "você investir na sua qualificação e dar um novo passo "
                "na sua trajetória profissional.\n\n"
                "Posso te explicar como funciona, apresentar as condições "
                "disponíveis e ajudar a encontrar a melhor opção para você.\n\n"
                "Você gostaria de receber informações sobre valores, "
                "horários e inscrição?"
            )

        if style == "follow_up":
            return (
                "Olá! Tudo bem?\n\n"
                f"Estou retomando nosso contato sobre {offering}. "
                "Você ainda tem interesse? Posso esclarecer suas dúvidas "
                "e ajudar com os próximos passos.\n\n"
                "Fico à disposição."
            )

        raise ValueError(f"Estilo comercial não suportado: {style or 'vazio'}")
