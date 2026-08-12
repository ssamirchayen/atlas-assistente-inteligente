from __future__ import annotations

import logging
from collections.abc import Iterable

from atlas.agents.base import (
    AgentMetadata,
    AgentSelection,
    SpecializedAgent,
)
from atlas.planner.actions import Action

_LOGGER = logging.getLogger(__name__)


class AgentRegistry:
    """Catálogo central e roteador determinístico de agentes."""

    def __init__(
        self,
        agents: Iterable[SpecializedAgent] | None = None,
    ) -> None:
        self._agents: dict[str, SpecializedAgent] = {}

        for agent in agents or ():
            self.register(agent)

    def register(self, agent: SpecializedAgent) -> None:
        if not isinstance(agent, SpecializedAgent):
            raise TypeError(
                "O agente deve declarar metadata e implementar plan()."
            )

        name = agent.metadata.name

        if name in self._agents:
            raise ValueError(f"Já existe um agente registrado como '{name}'.")

        self._agents[name] = agent

    def unregister(self, name: str) -> bool:
        return self._agents.pop(self._normalize_name(name), None) is not None

    def get(self, name: str) -> SpecializedAgent | None:
        return self._agents.get(self._normalize_name(name))

    def all(self) -> tuple[SpecializedAgent, ...]:
        return tuple(self._ordered_agents())

    def catalog(self) -> tuple[AgentMetadata, ...]:
        return tuple(agent.metadata for agent in self._ordered_agents())

    def route(
        self,
        command: str,
        *,
        candidates: Iterable[str] | None = None,
    ) -> AgentSelection | None:
        clean_command = command.strip()

        if not clean_command:
            return None

        allowed = (
            {
                self._normalize_name(name)
                for name in candidates
                if name and name.strip()
            }
            if candidates is not None
            else None
        )

        for agent in self._ordered_agents():
            if allowed is not None and agent.metadata.name not in allowed:
                continue

            try:
                actions = agent.plan(clean_command)
            except Exception:
                _LOGGER.exception(
                    "Falha não bloqueante no agente '%s'",
                    agent.metadata.name,
                )
                continue

            if not actions:
                continue

            if not all(isinstance(action, Action) for action in actions):
                _LOGGER.error(
                    "O agente '%s' retornou ações inválidas",
                    agent.metadata.name,
                )
                continue

            return AgentSelection(
                metadata=agent.metadata,
                actions=tuple(actions),
            )

        return None

    def _ordered_agents(self) -> list[SpecializedAgent]:
        return sorted(
            self._agents.values(),
            key=lambda agent: (
                -agent.metadata.priority,
                agent.metadata.name,
            ),
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip().lower()
