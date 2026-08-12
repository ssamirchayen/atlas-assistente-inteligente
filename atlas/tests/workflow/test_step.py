from __future__ import annotations

from atlas.planner.actions import Action
from atlas.workflow.condition import WorkflowCondition
from atlas.workflow.step import WorkflowStep


def test_step_stores_action():
    action = Action(
        type="mouse.click",
    )

    step = WorkflowStep(
        action=action,
    )

    assert step.action is action


def test_step_has_no_condition_by_default():
    action = Action(
        type="mouse.click",
    )

    step = WorkflowStep(
        action=action,
    )

    assert step.condition is None


def test_step_has_empty_metadata_by_default():
    action = Action(
        type="mouse.click",
    )

    step = WorkflowStep(
        action=action,
    )

    assert step.metadata == {}


def test_step_preserves_metadata():
    action = Action(
        type="browser.open",
        parameters={
            "url": "https://example.com",
        },
    )

    metadata = {
        "name": "Abrir site",
        "priority": 1,
    }

    step = WorkflowStep(
        action=action,
        metadata=metadata,
    )

    assert step.metadata == metadata


def test_should_execute_without_condition():
    action = Action(
        type="mouse.click",
    )

    step = WorkflowStep(
        action=action,
    )

    assert step.should_execute({}) is True


def test_should_execute_when_condition_is_true():
    action = Action(
        type="mouse.click",
    )

    condition = WorkflowCondition(
        field="logged_in",
        operator="==",
        value=True,
    )

    step = WorkflowStep(
        action=action,
        condition=condition,
    )

    context = {
        "logged_in": True,
    }

    assert step.should_execute(context) is True


def test_should_not_execute_when_condition_is_false():
    action = Action(
        type="mouse.click",
    )

    condition = WorkflowCondition(
        field="logged_in",
        operator="==",
        value=True,
    )

    step = WorkflowStep(
        action=action,
        condition=condition,
    )

    context = {
        "logged_in": False,
    }

    assert step.should_execute(context) is False


def test_should_execute_uses_context_values():
    action = Action(
        type="system.wait",
        parameters={
            "seconds": 1,
        },
    )

    condition = WorkflowCondition(
        field="attempts",
        operator="<",
        value=3,
    )

    step = WorkflowStep(
        action=action,
        condition=condition,
    )

    assert step.should_execute({"attempts": 2}) is True
    assert step.should_execute({"attempts": 3}) is False