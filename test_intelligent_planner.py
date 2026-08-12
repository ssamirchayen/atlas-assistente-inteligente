from __future__ import annotations

from atlas.context.manager import ContextManager
from atlas.planner.intelligent import IntelligentPlanner


def main() -> None:
    """Executa um teste manual do planejador usando o Ollama local."""
    context = ContextManager()
    planner = IntelligentPlanner(context=context)

    command = (
        "Crie uma pasta chamada Estudos "
        "e dentro dela crie um arquivo chamado python.txt"
    )

    actions = planner.plan(command)

    print("\nAções criadas:\n")

    if not actions:
        print(
            "Nenhuma ação foi criada. Verifique se o Ollama está "
            "aberto e se o modelo configurado está instalado."
        )
        return

    for action in actions:
        print(action)


if __name__ == "__main__":
    main()
