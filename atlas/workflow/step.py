from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from atlas.planner.actions import Action
from atlas.workflow.condition import WorkflowCondition


@dataclass(slots=True)
class WorkflowStep:
    """
    Representa uma etapa de um workflow.

    Uma etapa pode possuir:
    - uma ação a ser executada;
    - uma condição opcional;
    - metadados auxiliares.
    """

    action: Action
    condition: WorkflowCondition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def should_execute(
        self,
        context: dict[str, Any],
    ) -> bool:
        """
        Verifica se esta etapa deve ser executada.
        """

        if self.condition is None:
            return True

        return self.condition.evaluate(context)