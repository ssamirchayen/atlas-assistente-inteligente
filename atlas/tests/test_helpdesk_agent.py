from __future__ import annotations

import pytest

from atlas.agents.helpdesk import HelpDeskAgent
from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action


@pytest.mark.parametrize(
    ("command", "category"),
    (
        ("meu computador está sem internet", "network"),
        ("a impressora está offline", "printer"),
        ("meu microfone não funciona", "audio"),
        ("o computador está lento e travando", "performance"),
        ("o programa parou de funcionar", "application"),
        ("preciso de suporte técnico para um problema de TI", "general"),
    ),
)
def test_helpdesk_agent_classifies_incidents(
    command: str,
    category: str,
) -> None:
    actions = HelpDeskAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].type == "helpdesk.diagnose"
    assert actions[0].parameters["category"] == category
    assert actions[0].parameters["problem"] == command


def test_helpdesk_agent_ignores_unrelated_command() -> None:
    assert HelpDeskAgent().plan("abra a calculadora") == []


def test_helpdesk_agent_does_not_intercept_web_search() -> None:
    assert HelpDeskAgent().plan("pesquise erro de impressora") == []


def test_helpdesk_action_is_executed_by_automation_engine() -> None:
    result = AutomationEngine().execute(
        Action(
            type="helpdesk.diagnose",
            parameters={
                "category": "network",
                "problem": "meu computador está sem internet",
            },
        )
    )

    assert result.success is True
    assert result.action_type == "helpdesk.diagnose"
    assert "Diagnóstico inicial de rede" in result.message
    assert "outros dispositivos" in result.message


def test_helpdesk_action_rejects_unknown_category() -> None:
    result = AutomationEngine().execute(
        Action(
            type="helpdesk.diagnose",
            parameters={"category": "unknown", "problem": "erro"},
        )
    )

    assert result.success is False
    assert result.error_code == "invalid_parameter"
