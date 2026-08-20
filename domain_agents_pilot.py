"""Demonstra os agentes de domínio sem acessar rede ou alterar sistemas."""

from __future__ import annotations

from atlas.agents.industry import IndustrialOperationsAgent
from atlas.agents.programming import ProgrammingAdvisorAgent
from atlas.agents.radiology import RadiologySupportAgent
from atlas.agents.wholesale import WholesaleAgent
from atlas.automation.engine import AutomationEngine


def main() -> None:
    engine = AutomationEngine()
    scenarios = (
        (
            ProgrammingAdvisorAgent(),
            "crie um código em Python do zero para calcular média",
        ),
        (
            RadiologySupportAgent(),
            "verifique a qualidade e o posicionamento de uma radiografia",
        ),
        (WholesaleAgent(), "analise o giro de estoque no atacado"),
        (
            IndustrialOperationsAgent(),
            "analise a manutenção preventiva na indústria",
        ),
    )

    for agent, command in scenarios:
        actions = agent.plan(command)
        print(f"\n[{agent.metadata.display_name}] {command}")

        for action in actions:
            result = engine.execute(action)
            print(result)


if __name__ == "__main__":
    main()
