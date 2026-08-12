from __future__ import annotations

from atlas.reasoning.analyzer import IntentAnalysis, IntentAnalyzer
from atlas.reasoning.decision import Decision, DecisionType
from atlas.reasoning.intent import Intent
from atlas.reasoning.question import QuestionGenerator


class ReasoningEngine:
    """
    Analisa um comando e decide qual caminho o Atlas deve seguir.

    Este componente não executa automações e não cria ações.
    Ele apenas retorna uma Decision para o restante do sistema.
    """

    def __init__(
        self,
        analyzer: IntentAnalyzer | None = None,
        question_generator: QuestionGenerator | None = None,
        *,
        minimum_confidence: float = 0.45,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError(
                "minimum_confidence deve estar entre 0.0 e 1.0."
            )

        self.analyzer = analyzer or IntentAnalyzer()
        self.question_generator = (
            question_generator or QuestionGenerator()
        )
        self.minimum_confidence = minimum_confidence

    def reason(self, text: str) -> Decision:
        """
        Analisa o comando e retorna a decisão estratégica.
        """
        command = str(text).strip()

        if not command:
            return Decision(
                type=DecisionType.ASK,
                reason="empty_command",
                message="O que você deseja que eu faça?",
            )

        analysis = self.analyzer.analyze(command)

        if analysis.intent is Intent.UNKNOWN:
            return self._ask_for_clarification(
                command,
                analysis,
                reason="unknown_intent",
            )

        if (
            analysis.confidence < self.minimum_confidence
            and analysis.intent not in {
                Intent.CHAT,
                Intent.QUESTION,
            }
        ):
            return self._ask_for_clarification(
                command,
                analysis,
                reason="low_confidence",
            )

        return self._decide(command, analysis)

    def _decide(
        self,
        command: str,
        analysis: IntentAnalysis,
    ) -> Decision:
        """
        Seleciona uma decisão com base na intenção identificada.
        """
        intent = analysis.intent

        if intent is Intent.CHAT:
            return Decision(
                type=DecisionType.CHAT,
                reason="social_conversation",
                message=command,
            )

        if intent is Intent.QUESTION:
            return Decision(
                type=DecisionType.CHAT,
                reason="informational_question",
                message=command,
            )

        if intent is Intent.SEARCH:
            return Decision(
                type=DecisionType.SEARCH_BROWSER,
                reason="browser_search_requested",
                message=command,
            )

        if intent in {
            Intent.OPEN,
            Intent.FILE,
            Intent.WINDOW,
            Intent.CODE,
            Intent.SYSTEM,
        }:
            return Decision(
                type=DecisionType.EXECUTE,
                reason=f"direct_{intent.value}_command",
                message=command,
            )

        return Decision(
            type=DecisionType.PLAN,
            reason="complex_or_unclassified_command",
            message=command,
        )

    def _ask_for_clarification(
        self,
        command: str,
        analysis: IntentAnalysis,
        *,
        reason: str,
    ) -> Decision:
        question = self.question_generator.generate(
            command,
            analysis.intent,
        )

        return Decision(
            type=DecisionType.ASK,
            reason=reason,
            message=question,
        )