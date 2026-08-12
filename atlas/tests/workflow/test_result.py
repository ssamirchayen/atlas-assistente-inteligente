from __future__ import annotations

import pytest

from atlas.planner.results import ExecutionResult
from atlas.workflow.result import WorkflowResult


@pytest.fixture
def execution_results() -> list[ExecutionResult]:
    return [
        ExecutionResult.ok(
            action_type="browser.open",
            message="Site aberto.",
        ),
        ExecutionResult.ok(
            action_type="mouse.click",
            message="Clique executado.",
        ),
        ExecutionResult.ok(
            action_type="keyboard.press",
            message="Enter pressionado.",
        ),
    ]


def test_success_result(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult.success_result(
        execution_results,
    )

    assert result.success is True
    assert result.failed is False

    assert result.completed_steps == 3
    assert result.total_steps == 3

    assert result.completed_actions == 3
    assert result.total_actions == 3

    assert result.results == execution_results
    assert result.error is None


def test_failed_result(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult.failed_result(
        completed_steps=1,
        total_steps=3,
        results=execution_results[:1],
        error="Falha durante execução.",
    )

    assert result.success is False
    assert result.failed is True

    assert result.completed_steps == 1
    assert result.total_steps == 3

    assert result.completed_actions == 1
    assert result.total_actions == 3

    assert result.results == execution_results[:1]
    assert result.error == "Falha durante execução."


def test_progress_complete(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult.success_result(
        execution_results,
    )

    assert result.progress == 1.0


def test_progress_partial(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult.failed_result(
        completed_steps=2,
        total_steps=4,
        results=execution_results[:2],
        error="Erro",
    )

    assert result.progress == pytest.approx(0.5)


def test_progress_empty() -> None:
    result = WorkflowResult(
        success=True,
        completed_steps=0,
        total_steps=0,
    )

    assert result.progress == 1.0


def test_is_complete_true(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult.success_result(
        execution_results,
    )

    assert result.is_complete is True


def test_is_complete_false_when_failed(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult.failed_result(
        completed_steps=3,
        total_steps=3,
        results=execution_results,
        error="Erro",
    )

    assert result.is_complete is False


def test_is_complete_false_when_not_all_completed(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult(
        success=True,
        completed_steps=2,
        total_steps=3,
        results=execution_results[:2],
    )

    assert result.is_complete is False


def test_results_are_preserved(
    execution_results: list[ExecutionResult],
) -> None:
    result = WorkflowResult.success_result(
        execution_results,
    )

    assert len(result.results) == 3
    assert result.results[0].message == "Site aberto."
    assert result.results[1].message == "Clique executado."
    assert result.results[2].message == "Enter pressionado."


def test_failed_property() -> None:
    result = WorkflowResult(
        success=False,
        completed_steps=0,
        total_steps=1,
        error="Erro",
    )

    assert result.failed is True


def test_success_property() -> None:
    result = WorkflowResult(
        success=True,
        completed_steps=1,
        total_steps=1,
    )

    assert result.failed is False


def test_error_defaults_to_none() -> None:
    result = WorkflowResult(
        success=True,
        completed_steps=0,
        total_steps=0,
    )

    assert result.error is None


def test_results_default_to_empty_list() -> None:
    result = WorkflowResult(
        success=True,
        completed_steps=0,
        total_steps=0,
    )

    assert result.results == []


def test_compatibility_properties() -> None:
    result = WorkflowResult(
        success=True,
        completed_steps=2,
        total_steps=5,
    )

    assert result.completed_actions == result.completed_steps
    assert result.total_actions == result.total_steps