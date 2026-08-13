from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from atlas.agents.base import AgentMetadata
from atlas.agents.browser import BrowserAgent
from atlas.agents.coding import CodingAgent
from atlas.agents.desktop import DesktopAgent
from atlas.agents.registry import AgentRegistry
from atlas.agents.sales import SalesAgent
from atlas.planner.actions import Action


@dataclass
class StubAgent:
    metadata: AgentMetadata
    actions: list[Action] = field(default_factory=list)
    error: Exception | None = None
    commands: list[str] = field(default_factory=list)

    def plan(self, command: str) -> list[Action]:
        self.commands.append(command)

        if self.error is not None:
            raise self.error

        return list(self.actions)


def make_agent(
    name: str,
    *,
    priority: int,
    action_type: str | None = None,
) -> StubAgent:
    actions = [Action(action_type)] if action_type else []
    return StubAgent(
        metadata=AgentMetadata(
            name=name,
            display_name=f"{name.title()} Agent",
            description=f"Agente especializado em {name}.",
            domains=(name,),
            priority=priority,
        ),
        actions=actions,
    )


def test_metadata_normalizes_identity_and_domains() -> None:
    metadata = AgentMetadata(
        name="  SALES ",
        display_name=" Sales Agent ",
        description=" Atendimento comercial. ",
        domains=(" Sales ", "CRM"),
    )

    assert metadata.name == "sales"
    assert metadata.display_name == "Sales Agent"
    assert metadata.description == "Atendimento comercial."
    assert metadata.domains == ("sales", "crm")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("display_name", ""),
        ("description", ""),
        ("domains", ()),
    ],
)
def test_metadata_rejects_incomplete_agents(field: str, value: object) -> None:
    values = {
        "name": "sales",
        "display_name": "Sales Agent",
        "description": "Atendimento comercial.",
        "domains": ("sales",),
    }
    values[field] = value

    with pytest.raises(ValueError):
        AgentMetadata(**values)


def test_registry_routes_by_priority() -> None:
    low = make_agent("desktop", priority=100, action_type="desktop.open")
    high = make_agent("browser", priority=300, action_type="browser.open")
    registry = AgentRegistry((low, high))

    selection = registry.route("abra alguma coisa")

    assert selection is not None
    assert selection.agent_name == "browser"
    assert selection.actions[0].type == "browser.open"
    assert high.commands == ["abra alguma coisa"]
    assert low.commands == []


def test_registry_filters_candidates_without_changing_global_priority() -> None:
    browser = make_agent("browser", priority=300, action_type="browser.open")
    desktop = make_agent("desktop", priority=100, action_type="process.start")
    registry = AgentRegistry((browser, desktop))

    selection = registry.route(
        "abra a calculadora",
        candidates=("desktop",),
    )

    assert selection is not None
    assert selection.agent_name == "desktop"
    assert browser.commands == []
    assert desktop.commands == ["abra a calculadora"]


def test_registry_continues_when_agent_does_not_handle_command() -> None:
    high = make_agent("browser", priority=300)
    low = make_agent("desktop", priority=100, action_type="process.start")
    registry = AgentRegistry((high, low))

    selection = registry.route("abra a calculadora")

    assert selection is not None
    assert selection.agent_name == "desktop"
    assert high.commands == ["abra a calculadora"]
    assert low.commands == ["abra a calculadora"]


def test_registry_isolates_agent_failure() -> None:
    broken = make_agent("broken", priority=500)
    broken.error = RuntimeError("falha interna")
    healthy = make_agent("healthy", priority=100, action_type="system.wait")
    registry = AgentRegistry((broken, healthy))

    selection = registry.route("execute")

    assert selection is not None
    assert selection.agent_name == "healthy"


def test_registry_rejects_duplicate_agent_name() -> None:
    registry = AgentRegistry((make_agent("sales", priority=100),))

    with pytest.raises(ValueError, match="Já existe"):
        registry.register(make_agent("SALES", priority=200))


def test_catalog_contains_existing_agents_in_priority_order() -> None:
    registry = AgentRegistry(
        (
            DesktopAgent(),
            CodingAgent(),
            SalesAgent(),
            BrowserAgent(),
        )
    )

    assert [metadata.name for metadata in registry.catalog()] == [
        "browser",
        "sales",
        "coding",
        "desktop",
    ]
    assert all(metadata.domains for metadata in registry.catalog())
