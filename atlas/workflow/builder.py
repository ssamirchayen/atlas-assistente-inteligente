from __future__ import annotations

from atlas.planner.actions import Action
from atlas.workflow.step import WorkflowStep


class WorkflowBuilder:
    """
    Converte ações planejadas em etapas de workflow.
    """

    def build(
        self,
        actions: list[Action],
    ) -> list[WorkflowStep]:

        return [
            WorkflowStep(
                action=action,
            )
            for action in actions
        ]