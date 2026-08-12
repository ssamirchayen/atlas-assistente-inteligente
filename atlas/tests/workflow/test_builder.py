from __future__ import annotations

from atlas.planner.actions import Action
from atlas.workflow.builder import WorkflowBuilder
from atlas.workflow.step import WorkflowStep


def test_build_returns_empty_list_when_there_are_no_actions():
    builder = WorkflowBuilder()

    steps = builder.build([])

    assert steps == []


def test_build_creates_one_step_for_each_action():
    builder = WorkflowBuilder()

    actions = [
        Action(
            type="browser.open",
            parameters={
                "url": "https://example.com",
            },
        ),
        Action(
            type="mouse.click",
        ),
        Action(
            type="keyboard.press",
            parameters={
                "key": "enter",
            },
        ),
    ]

    steps = builder.build(actions)

    assert len(steps) == len(actions)


def test_build_returns_workflow_steps():
    builder = WorkflowBuilder()

    actions = [
        Action(
            type="mouse.click",
        ),
        Action(
            type="system.wait",
            parameters={
                "seconds": 1,
            },
        ),
    ]

    steps = builder.build(actions)

    assert all(
        isinstance(step, WorkflowStep)
        for step in steps
    )


def test_build_preserves_action_order():
    builder = WorkflowBuilder()

    first_action = Action(
        type="browser.open",
    )

    second_action = Action(
        type="mouse.click",
    )

    third_action = Action(
        type="keyboard.press",
        parameters={
            "key": "enter",
        },
    )

    actions = [
        first_action,
        second_action,
        third_action,
    ]

    steps = builder.build(actions)

    assert steps[0].action is first_action
    assert steps[1].action is second_action
    assert steps[2].action is third_action


def test_build_preserves_action_instances():
    builder = WorkflowBuilder()

    action = Action(
        type="browser.search",
        parameters={
            "query": "Atlas",
        },
    )

    steps = builder.build(
        [
            action,
        ]
    )

    assert steps[0].action is action


def test_build_creates_steps_without_conditions():
    builder = WorkflowBuilder()

    action = Action(
        type="mouse.click",
    )

    steps = builder.build(
        [
            action,
        ]
    )

    assert steps[0].condition is None


def test_build_creates_steps_with_empty_metadata():
    builder = WorkflowBuilder()

    action = Action(
        type="mouse.click",
    )

    steps = builder.build(
        [
            action,
        ]
    )

    assert steps[0].metadata == {}