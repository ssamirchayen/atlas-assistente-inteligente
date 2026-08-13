from __future__ import annotations

import pytest

from atlas.agents.sales import SalesAgent
from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action


def test_sales_agent_plans_commercial_approach() -> None:
    actions = SalesAgent().plan(
        "Crie uma mensagem de vendas para o curso de Radiologia"
    )

    assert actions == [
        Action(
            type="sales.compose_message",
            parameters={
                "style": "approach",
                "offering": "curso de Radiologia",
            },
        )
    ]


def test_sales_agent_plans_follow_up_for_interested_customer() -> None:
    actions = SalesAgent().plan(
        "Faça um follow-up para um cliente interessado no curso de ADS"
    )

    assert actions[0].parameters == {
        "style": "follow_up",
        "offering": "curso de ADS",
    }


def test_sales_agent_ignores_unrelated_command() -> None:
    assert SalesAgent().plan("abra o navegador") == []


def test_sales_action_is_executed_by_automation_engine() -> None:
    engine = AutomationEngine()

    result = engine.execute(
        Action(
            type="sales.compose_message",
            parameters={
                "style": "approach",
                "offering": "curso de Radiologia",
            },
        )
    )

    assert result.success is True
    assert result.action_type == "sales.compose_message"
    assert "curso de Radiologia" in result.message
    assert "investir na sua qualificação" in result.message
    assert "valores, horários e inscrição" in result.message


def test_sales_action_rejects_unknown_style() -> None:
    engine = AutomationEngine()

    result = engine.execute(
        Action(
            type="sales.compose_message",
            parameters={"style": "unknown", "offering": "produto"},
        )
    )

    assert result.success is False
    assert result.error_code == "invalid_parameter"


@pytest.mark.parametrize(
    "command",
    (
        "crie uma abordagem comercial para um serviço de suporte",
        "faça um texto de venda sobre consultoria em TI",
        "crie uma mensagem para vender o curso de Eletrotécnica",
        "crie uma mensagem de renda para o curso de Radiologia",
    ),
)
def test_sales_agent_accepts_approach_variants(command: str) -> None:
    actions = SalesAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].type == "sales.compose_message"
    assert actions[0].parameters["style"] == "approach"
