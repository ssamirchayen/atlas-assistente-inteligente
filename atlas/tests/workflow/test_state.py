from __future__ import annotations

import pytest

from atlas.planner.actions import Action
from atlas.workflow.state import WorkflowState
from atlas.workflow.step import WorkflowStep


@pytest.fixture
def steps() -> list[WorkflowStep]:
    return [
        WorkflowStep(
            action=Action(
                type="browser.open",
                parameters={"url": "https://example.com"},
            )
        ),
        WorkflowStep(
            action=Action(
                type="mouse.click",
            )
        ),
        WorkflowStep(
            action=Action(
                type="keyboard.press",
                parameters={"key": "enter"},
            )
        ),
    ]


@pytest.fixture
def state(steps: list[WorkflowStep]) -> WorkflowState:
    return WorkflowState(steps=steps)


def test_initial_state(state: WorkflowState):
    assert state.current_index == 0
    assert state.current_step is None
    assert state.completed_steps == []
    assert state.skipped_steps == []
    assert state.failed_steps == []
    assert state.finished is False
    assert state.failed is False
    assert state.error is None
    assert state.progress == 0.0


def test_has_next(state: WorkflowState):
    assert state.has_next is True


def test_next_step_returns_first_step(
    state: WorkflowState,
    steps: list[WorkflowStep],
):
    step = state.next_step()

    assert step is steps[0]
    assert state.current_step is steps[0]


def test_mark_completed(
    state: WorkflowState,
    steps: list[WorkflowStep],
):
    state.next_step()
    state.mark_completed()

    assert state.completed_steps == [steps[0]]
    assert state.current_step is None
    assert state.current_index == 1


def test_mark_skipped(
    state: WorkflowState,
    steps: list[WorkflowStep],
):
    state.next_step()
    state.mark_skipped()

    assert state.skipped_steps == [steps[0]]
    assert state.current_index == 1


def test_mark_failed(
    state: WorkflowState,
    steps: list[WorkflowStep],
):
    state.next_step()
    state.mark_failed("erro")

    assert state.failed_steps == [steps[0]]
    assert state.failed is True
    assert state.finished is True
    assert state.error == "erro"


def test_progress_after_completed(state: WorkflowState):
    state.next_step()
    state.mark_completed()

    assert state.progress == pytest.approx(1 / 3)


def test_progress_after_skipped(state: WorkflowState):
    state.next_step()
    state.mark_skipped()

    assert state.progress == pytest.approx(1 / 3)


def test_progress_after_failed(state: WorkflowState):
    state.next_step()
    state.mark_failed("erro")

    assert state.progress == pytest.approx(1 / 3)


def test_workflow_finishes_after_all_steps(state: WorkflowState):
    while state.has_next:
        state.next_step()
        state.mark_completed()

    assert state.finished is True
    assert state.progress == 1.0


def test_next_step_returns_none_when_finished(
    state: WorkflowState,
):
    while state.has_next:
        state.next_step()
        state.mark_completed()

    assert state.next_step() is None


def test_fail_sets_flags(state: WorkflowState):
    state.fail("falhou")

    assert state.failed is True
    assert state.finished is True
    assert state.error == "falhou"


def test_reset_restores_initial_state(
    state: WorkflowState,
):
    state.next_step()
    state.mark_completed()
    state.context.set("teste", 123)
    state.fail("erro")

    state.reset()

    assert state.current_index == 0
    assert state.current_step is None
    assert state.completed_steps == []
    assert state.skipped_steps == []
    assert state.failed_steps == []
    assert state.finished is False
    assert state.failed is False
    assert state.error is None
    assert state.context.data == {}


def test_metadata_property(
    state: WorkflowState,
):
    state.metadata["id"] = 10

    assert state.context.get("id") == 10


def test_actions_property(
    state: WorkflowState,
):
    actions = state.actions

    assert len(actions) == 3
    assert actions[0].type == "browser.open"
    assert actions[1].type == "mouse.click"


def test_completed_actions_property(
    state: WorkflowState,
):
    state.next_step()
    state.mark_completed()

    completed = state.completed_actions

    assert len(completed) == 1
    assert completed[0].type == "browser.open"


def test_current_action_property(
    state: WorkflowState,
):
    assert state.current_action is None

    state.next_step()

    assert state.current_action.type == "browser.open"


def test_empty_workflow():
    state = WorkflowState(steps=[])

    assert state.has_next is False
    assert state.progress == 1.0
    assert state.next_step() is None