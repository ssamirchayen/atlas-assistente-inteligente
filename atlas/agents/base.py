from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlas.planner.actions import Action


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    """Identidade e capacidades declaradas por um agente do Atlas."""

    name: str
    display_name: str
    description: str
    domains: tuple[str, ...]
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("O nome interno do agente é obrigatório.")

        if not self.display_name or not self.display_name.strip():
            raise ValueError("O nome de exibição do agente é obrigatório.")

        if not self.description or not self.description.strip():
            raise ValueError("A descrição do agente é obrigatória.")

        normalized_name = self.name.strip().lower()
        normalized_domains = tuple(
            domain.strip().lower()
            for domain in self.domains
            if domain and domain.strip()
        )

        if not normalized_domains:
            raise ValueError("O agente deve declarar ao menos um domínio.")

        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "display_name", self.display_name.strip())
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "domains", normalized_domains)


@runtime_checkable
class SpecializedAgent(Protocol):
    """Contrato mínimo para qualquer agente especializado do Atlas."""

    metadata: AgentMetadata

    def plan(self, command: str) -> list[Action]:
        """Transforma um comando compatível em ações executáveis."""


@dataclass(frozen=True, slots=True)
class AgentSelection:
    """Resultado do agente selecionado para um comando."""

    metadata: AgentMetadata
    actions: tuple[Action, ...]

    @property
    def agent_name(self) -> str:
        return self.metadata.name
