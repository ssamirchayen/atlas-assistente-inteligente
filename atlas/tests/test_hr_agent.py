from __future__ import annotations

import pytest

from atlas.agents.hr import HRAgent
from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action


@pytest.mark.parametrize(
    ("command", "document_type", "role"),
    (
        (
            "crie uma descrição de vaga para desenvolvedor Python",
            "job_description",
            "desenvolvedor Python",
        ),
        (
            "crie um roteiro de entrevista para analista de suporte",
            "interview_guide",
            "analista de suporte",
        ),
        (
            "crie critérios de triagem para a vaga de help desk",
            "screening_criteria",
            "help desk",
        ),
    ),
)
def test_hr_agent_plans_structured_documents(
    command: str,
    document_type: str,
    role: str,
) -> None:
    actions = HRAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].type == "hr.generate_document"
    assert actions[0].parameters["document_type"] == document_type
    assert actions[0].parameters["role"] == role


@pytest.mark.parametrize(
    ("command", "status"),
    (
        (
            "crie uma mensagem para candidato aprovado na vaga de suporte",
            "approved",
        ),
        (
            "crie um convite para entrevista da vaga de suporte",
            "interview_invitation",
        ),
        (
            "crie uma mensagem para candidato não selecionado na vaga de "
            "suporte",
            "not_selected",
        ),
    ),
)
def test_hr_agent_identifies_candidate_status(
    command: str,
    status: str,
) -> None:
    actions = HRAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].parameters["document_type"] == "candidate_message"
    assert actions[0].parameters["status"] == status
    assert actions[0].parameters["role"] == "suporte"


def test_hr_agent_has_priority_over_helpdesk_context() -> None:
    actions = HRAgent().plan(
        "crie uma descrição de vaga para analista de help desk"
    )

    assert actions[0].parameters["document_type"] == "job_description"
    assert actions[0].parameters["role"] == "analista de help desk"


def test_hr_agent_ignores_unrelated_command_and_explicit_search() -> None:
    agent = HRAgent()

    assert agent.plan("abra a calculadora") == []
    assert agent.plan("pesquise vagas de desenvolvedor Python") == []


@pytest.mark.parametrize(
    ("document_type", "expected_text"),
    (
        ("job_description", "DESCRIÇÃO DA VAGA"),
        ("interview_guide", "ROTEIRO DE ENTREVISTA"),
        ("screening_criteria", "revisão humana"),
    ),
)
def test_hr_action_generates_documents(
    document_type: str,
    expected_text: str,
) -> None:
    result = AutomationEngine().execute(
        Action(
            type="hr.generate_document",
            parameters={
                "document_type": document_type,
                "role": "analista de suporte",
            },
        )
    )

    assert result.success is True
    assert result.action_type == "hr.generate_document"
    assert expected_text in result.message


def test_screening_criteria_excludes_personal_characteristics() -> None:
    result = AutomationEngine().execute(
        Action(
            type="hr.generate_document",
            parameters={
                "document_type": "screening_criteria",
                "role": "analista de suporte",
            },
        )
    )

    assert "Não utilize idade, gênero, raça" in result.message
    assert "revisão humana" in result.message


def test_hr_action_rejects_unknown_document() -> None:
    result = AutomationEngine().execute(
        Action(
            type="hr.generate_document",
            parameters={"document_type": "unknown", "role": "suporte"},
        )
    )

    assert result.success is False
    assert result.error_code == "invalid_parameter"
