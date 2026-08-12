from __future__ import annotations

from atlas.workflow.context import WorkflowContext


def test_set_and_get():
    context = WorkflowContext()

    context.set("user", "Ssamir")

    assert context.get("user") == "Ssamir"


def test_get_default_value():
    context = WorkflowContext()

    assert context.get("missing") is None
    assert context.get("missing", 123) == 123


def test_exists():
    context = WorkflowContext()

    context.set("x", 10)

    assert context.exists("x")
    assert not context.exists("y")


def test_remove():
    context = WorkflowContext()

    context.set("name", "Atlas")

    context.remove("name")

    assert not context.exists("name")


def test_remove_missing_key_does_not_fail():
    context = WorkflowContext()

    context.remove("missing")

    assert context.as_dict() == {}


def test_update():
    context = WorkflowContext()

    context.update(
        {
            "a": 1,
            "b": 2,
        }
    )

    assert context.get("a") == 1
    assert context.get("b") == 2


def test_set_result():
    context = WorkflowContext()

    context.set_result("result1")
    context.set_result("result2")

    assert context.results == [
        "result1",
        "result2",
    ]


def test_last_result():
    context = WorkflowContext()

    assert context.last_result() is None

    context.set_result("first")
    context.set_result("second")

    assert context.last_result() == "second"


def test_add_history():
    context = WorkflowContext()

    context.add_history(
        "step_completed",
        action="click",
        success=True,
    )

    assert len(context.history) == 1

    event = context.history[0]

    assert event["event"] == "step_completed"
    assert event["action"] == "click"
    assert event["success"] is True


def test_as_dict_returns_copy():
    context = WorkflowContext()

    context.set("name", "Atlas")

    data = context.as_dict()

    data["name"] = "Modified"

    assert context.get("name") == "Atlas"


def test_clear():
    context = WorkflowContext()

    context.set("x", 1)
    context.set_result("result")

    context.add_history(
        "event",
        value=1,
    )

    context.clear()

    assert context.as_dict() == {}
    assert context.results == []
    assert context.history == []