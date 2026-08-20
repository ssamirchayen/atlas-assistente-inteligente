from __future__ import annotations

import pytest

from atlas.agents.wholesale import WholesaleAgent
from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action


@pytest.mark.parametrize(
    ("command", "mode"),
    (
        ("analise o giro de estoque no atacado", "inventory"),
        ("avalie a margem de produto do atacadista", "pricing"),
        ("faça uma previsão de demanda para o distribuidor", "demand"),
        ("avalie a rota de entrega do centro de distribuição", "logistics"),
    ),
)
def test_wholesale_agent_classifies_analysis(
    command: str,
    mode: str,
) -> None:
    actions = WholesaleAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].type == "domain.wholesale_analysis"
    assert actions[0].parameters["mode"] == mode


def test_wholesale_agent_ignores_unrelated_command() -> None:
    assert WholesaleAgent().plan("abra o navegador") == []


def test_wholesale_action_is_advisory_only() -> None:
    prompts: list[str] = []

    def respond(prompt: str) -> str:
        prompts.append(prompt)
        return "Recomendação de estoque aguardando aprovação humana."

    result = AutomationEngine(domain_responder=respond).execute(
        Action(
            type="domain.wholesale_analysis",
            parameters={
                "mode": "inventory",
                "request": "analise o giro de estoque no atacado",
            },
        )
    )

    assert result.success is True
    assert "aprovação humana" in result.message
    assert "Não altere preços, estoque, pedidos ou cadastros" in prompts[0]


def test_wholesale_action_rejects_unknown_mode() -> None:
    result = AutomationEngine().execute(
        Action(
            type="domain.wholesale_analysis",
            parameters={"mode": "purchase", "request": "compre agora"},
        )
    )

    assert result.success is False
    assert result.error_code == "invalid_parameter"
