from __future__ import annotations

import pytest

from atlas.agents.programming import ProgrammingAdvisorAgent
from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action


@pytest.mark.parametrize(
    ("command", "mode", "language"),
    (
        ("crie um código em Python do zero", "create", "Python"),
        ("revise este código em TypeScript", "review", "TypeScript"),
        ("encontre o bug neste código Java", "debug", "Java"),
        ("analise a segurança deste código PHP", "security", "PHP"),
    ),
)
def test_programming_agent_classifies_request(
    command: str,
    mode: str,
    language: str,
) -> None:
    actions = ProgrammingAdvisorAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].type == "domain.programming_assist"
    assert actions[0].parameters == {
        "mode": mode,
        "language": language,
        "request": command,
    }


def test_programming_agent_ignores_project_automation() -> None:
    assert ProgrammingAdvisorAgent().plan("abra o projeto Atlas") == []


def test_programming_agent_handles_radiology_software_request() -> None:
    actions = ProgrammingAdvisorAgent().plan(
        "crie um sistema para organizar exames de raio X"
    )

    assert actions[0].type == "domain.programming_assist"
    assert actions[0].parameters["mode"] == "create"


def test_programming_action_uses_text_only_responder() -> None:
    prompts: list[str] = []

    def respond(prompt: str) -> str:
        prompts.append(prompt)
        return "Plano de código com testes e validação."

    result = AutomationEngine(domain_responder=respond).execute(
        Action(
            type="domain.programming_assist",
            parameters={
                "mode": "create",
                "language": "Python",
                "request": "crie uma função para calcular média",
            },
        )
    )

    assert result.success is True
    assert result.message == "Plano de código com testes e validação."
    assert len(prompts) == 1
    assert "Não execute código" in prompts[0]
    assert "não invente resultados de testes" in prompts[0]


def test_programming_action_rejects_unknown_mode() -> None:
    result = AutomationEngine().execute(
        Action(
            type="domain.programming_assist",
            parameters={
                "mode": "execute",
                "language": "Python",
                "request": "execute este código",
            },
        )
    )

    assert result.success is False
    assert result.error_code == "invalid_parameter"
