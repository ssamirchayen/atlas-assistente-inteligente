from __future__ import annotations

import pytest

from atlas.workflow.condition import WorkflowCondition


def test_equal_operator():
    condition = WorkflowCondition(
        field="status",
        operator="==",
        value="ok",
    )

    assert condition.evaluate({"status": "ok"}) is True
    assert condition.evaluate({"status": "erro"}) is False


def test_not_equal_operator():
    condition = WorkflowCondition(
        field="status",
        operator="!=",
        value="erro",
    )

    assert condition.evaluate({"status": "ok"}) is True
    assert condition.evaluate({"status": "erro"}) is False


def test_greater_than_operator():
    condition = WorkflowCondition(
        field="value",
        operator=">",
        value=10,
    )

    assert condition.evaluate({"value": 20}) is True
    assert condition.evaluate({"value": 10}) is False
    assert condition.evaluate({"value": 5}) is False


def test_less_than_operator():
    condition = WorkflowCondition(
        field="value",
        operator="<",
        value=10,
    )

    assert condition.evaluate({"value": 5}) is True
    assert condition.evaluate({"value": 10}) is False
    assert condition.evaluate({"value": 20}) is False


def test_greater_or_equal_operator():
    condition = WorkflowCondition(
        field="value",
        operator=">=",
        value=10,
    )

    assert condition.evaluate({"value": 10}) is True
    assert condition.evaluate({"value": 15}) is True
    assert condition.evaluate({"value": 5}) is False


def test_less_or_equal_operator():
    condition = WorkflowCondition(
        field="value",
        operator="<=",
        value=10,
    )

    assert condition.evaluate({"value": 10}) is True
    assert condition.evaluate({"value": 5}) is True
    assert condition.evaluate({"value": 15}) is False


def test_missing_field_returns_false_for_equal():
    condition = WorkflowCondition(
        field="missing",
        operator="==",
        value="x",
    )

    assert condition.evaluate({}) is False


def test_invalid_operator():
    condition = WorkflowCondition(
        field="value",
        operator="===",
        value=1,
    )

    with pytest.raises(ValueError, match="Operador inválido"):
        condition.evaluate({"value": 1})