from __future__ import annotations

import pytest

from atlas.agents.radiology import RadiologySupportAgent
from atlas.automation.engine import AutomationEngine
from atlas.planner.actions import Action


@pytest.mark.parametrize(
    ("command", "mode"),
    (
        ("apoie a avaliação desta radiografia", "clinical_support"),
        ("verifique a qualidade e o posicionamento do raio X", "quality_check"),
        ("organize a fila de exames de radiologia", "worklist"),
    ),
)
def test_radiology_agent_classifies_support_request(
    command: str,
    mode: str,
) -> None:
    actions = RadiologySupportAgent().plan(command)

    assert len(actions) == 1
    assert actions[0].type == "domain.radiology_support"
    assert actions[0].parameters["mode"] == mode
    assert actions[0].parameters["human_review_required"] is True


def test_radiology_agent_does_not_intercept_software_project() -> None:
    assert (
        RadiologySupportAgent().plan(
            "crie um sistema para organizar exames de raio X"
        )
        == []
    )


def test_radiology_support_does_not_claim_diagnosis_or_pixel_analysis() -> None:
    result = AutomationEngine().execute(
        Action(
            type="domain.radiology_support",
            parameters={
                "mode": "clinical_support",
                "request": "analise esta radiografia",
                "human_review_required": True,
            },
        )
    )

    assert result.success is True
    assert "não recebe pixels" in result.message
    assert "não identifica patologias" in result.message
    assert "não emite diagnóstico ou laudo" in result.message
    assert "profissional habilitado" in result.message


def test_radiology_support_requires_professional_review() -> None:
    result = AutomationEngine().execute(
        Action(
            type="domain.radiology_support",
            parameters={
                "mode": "quality_check",
                "request": "verifique a qualidade do exame",
                "human_review_required": False,
            },
        )
    )

    assert result.success is False
    assert result.error_code == "invalid_parameter"
