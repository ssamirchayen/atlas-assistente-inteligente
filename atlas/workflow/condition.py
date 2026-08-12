from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class WorkflowCondition:
    """
    Representa uma condição de execução de um workflow.
    """

    field: str
    operator: str
    value: Any

    def evaluate(self, context: dict[str, Any]) -> bool:
        current = context.get(self.field)

        match self.operator:
            case "==":
                return current == self.value

            case "!=":
                return current != self.value

            case ">":
                return current > self.value

            case "<":
                return current < self.value

            case ">=":
                return current >= self.value

            case "<=":
                return current <= self.value

            case _:
                raise ValueError(
                    f"Operador inválido: {self.operator}"
                )