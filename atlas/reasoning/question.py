from __future__ import annotations

from atlas.reasoning.intent import Intent


class QuestionGenerator:
    """
    Gera perguntas de esclarecimento quando o comando não possui
    informações suficientes para uma execução segura.
    """

    def generate(self, text: str, intent: Intent) -> str:
        command = text.strip()

        questions: dict[Intent, str] = {
            Intent.OPEN: (
                "O que você deseja que eu abra?"
            ),
            Intent.SEARCH: (
                "O que você deseja que eu pesquise?"
            ),
            Intent.FILE: (
                "Qual arquivo ou pasta você deseja utilizar?"
            ),
            Intent.WINDOW: (
                "Qual janela você deseja controlar?"
            ),
            Intent.CODE: (
                "O que você deseja que eu faça no projeto ou no código?"
            ),
            Intent.SYSTEM: (
                "Qual ação você deseja executar no computador?"
            ),
            Intent.QUESTION: (
                "Você pode explicar um pouco melhor a sua pergunta?"
            ),
            Intent.UNKNOWN: (
                "Não entendi completamente. Você pode explicar "
                "o que deseja que eu faça?"
            ),
        }

        question = questions.get(
            intent,
            "Você pode fornecer mais detalhes sobre o que deseja?",
        )

        if command:
            return f'{question} Seu pedido foi: "{command}".'

        return question