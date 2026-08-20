from __future__ import annotations

import pytest

from atlas.agents.industry import IndustrialOperationsAgent
from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action


@pytest.mark.parametrize(
    ("command", "mode"),
    (
        ("avalie os riscos NR 12 na indústria", "safety"),
        ("analise a manutenção preventiva da linha", "maintenance"),
        ("analise os defeitos e retrabalho industrial", "quality"),
        ("calcule o OEE da linha de produção", "production"),
    ),
)
def test_industry_agent_classifies_analysis(
    command: str,
    mode: str,
) -> None:
    actions = IndustrialOperationsAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].type == "domain.industry_analysis"
    assert actions[0].parameters["mode"] == mode
    assert actions[0].parameters["machine_control"] is False


def test_industry_agent_ignores_unrelated_command() -> None:
    assert IndustrialOperationsAgent().plan("liste minhas memórias") == []


def test_industry_action_never_controls_machines() -> None:
    prompts: list[str] = []

    def respond(prompt: str) -> str:
        prompts.append(prompt)
        return "Hipóteses de manutenção para validação da engenharia."

    result = AutomationEngine(domain_responder=respond).execute(
        Action(
            type="domain.industry_analysis",
            parameters={
                "mode": "maintenance",
                "request": "avalie uma parada da linha industrial",
                "machine_control": False,
            },
        )
    )

    assert result.success is True
    assert "validação da engenharia" in result.message
    assert "Não controle máquinas" in prompts[0]
    assert "não altere PLC" in prompts[0]


def test_industry_action_rejects_machine_control() -> None:
    result = AutomationEngine().execute(
        Action(
            type="domain.industry_analysis",
            parameters={
                "mode": "production",
                "request": "altere a linha",
                "machine_control": True,
            },
        )
    )

    assert result.success is False
    assert result.error_code == "invalid_parameter"
