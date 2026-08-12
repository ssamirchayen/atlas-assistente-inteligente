from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from atlas.reasoning.intent import Intent


@dataclass(slots=True, frozen=True)
class IntentAnalysis:
    """
    Resultado detalhado da análise de intenção.

    intent:
        Intenção principal identificada.

    confidence:
        Confiança estimada entre 0.0 e 1.0.

    matched_terms:
        Termos encontrados no comando.

    normalized_text:
        Texto normalizado usado durante a análise.
    """

    intent: Intent
    confidence: float
    matched_terms: tuple[str, ...]
    normalized_text: str


class IntentAnalyzer:
    """
    Identifica a intenção principal de um comando do usuário.

    O analyzer não cria ações e não executa comandos.
    Ele apenas classifica o texto recebido.
    """

    def __init__(self) -> None:
        self._patterns: dict[Intent, tuple[str, ...]] = {
            Intent.OPEN: (
                "abra",
                "abrir",
                "abre",
                "inicie",
                "iniciar",
                "execute",
                "executar",
                "rode",
                "rodar",
                "acessar",
                "acesse",
            ),
            Intent.SEARCH: (
                "pesquise",
                "pesquisar",
                "procure",
                "procurar",
                "busque",
                "buscar",
                "google",
                "googlear",
                "youtube",
                "encontre",
                "encontrar",
            ),
            Intent.FILE: (
                "arquivo",
                "pasta",
                "diretorio",
                "crie uma pasta",
                "criar uma pasta",
                "crie um arquivo",
                "criar um arquivo",
                "apague o arquivo",
                "deletar arquivo",
                "excluir arquivo",
                "renomear arquivo",
                "mover arquivo",
                "copiar arquivo",
            ),
            Intent.WINDOW: (
                "janela",
                "minimize",
                "minimizar",
                "maximize",
                "maximizar",
                "restaure",
                "restaurar",
                "feche a janela",
                "fechar janela",
                "troque de janela",
                "proxima janela",
                "janela anterior",
                "area de trabalho",
            ),
            Intent.CODE: (
                "codigo",
                "programar",
                "programacao",
                "python",
                "javascript",
                "html",
                "css",
                "funcao",
                "classe",
                "bug",
                "erro no codigo",
                "corrigir codigo",
                "criar projeto",
                "vs code",
                "vscode",
            ),
            Intent.SYSTEM: (
                "computador",
                "sistema",
                "windows",
                "desligar",
                "reiniciar",
                "bloquear computador",
                "volume",
                "wifi",
                "internet",
                "processo",
                "programa",
                "aplicativo",
            ),
            Intent.QUESTION: (
                "como",
                "porque",
                "por que",
                "qual",
                "quais",
                "quando",
                "onde",
                "quem",
                "quanto",
                "o que",
                "oque",
                "explique",
                "me explique",
            ),
            Intent.CHAT: (
                "ola",
                "oi",
                "bom dia",
                "boa tarde",
                "boa noite",
                "tudo bem",
                "obrigado",
                "obrigada",
                "valeu",
                "como voce esta",
            ),
        }

        self._priority: tuple[Intent, ...] = (
            Intent.FILE,
            Intent.WINDOW,
            Intent.CODE,
            Intent.SEARCH,
            Intent.OPEN,
            Intent.SYSTEM,
            Intent.QUESTION,
            Intent.CHAT,
        )

    def detect(self, text: str) -> Intent:
        """
        Retorna apenas a intenção principal.
        """
        return self.analyze(text).intent

    def analyze(self, text: str) -> IntentAnalysis:
        """
        Analisa o texto e retorna intenção, confiança e termos encontrados.
        """
        normalized_text = self._normalize(text)

        if not normalized_text:
            return IntentAnalysis(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                matched_terms=(),
                normalized_text="",
            )

        scores: dict[Intent, int] = {}
        matches: dict[Intent, list[str]] = {}

        for intent, terms in self._patterns.items():
            intent_score = 0
            intent_matches: list[str] = []

            for term in terms:
                normalized_term = self._normalize(term)

                if self._contains_term(normalized_text, normalized_term):
                    intent_matches.append(term)

                    # Expressões maiores e mais específicas recebem mais peso.
                    word_count = len(normalized_term.split())

                    if word_count >= 3:
                        intent_score += 4
                    elif word_count == 2:
                        intent_score += 3
                    else:
                        intent_score += 1

            if intent_score > 0:
                scores[intent] = intent_score
                matches[intent] = intent_matches

        if not scores:
            return IntentAnalysis(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                matched_terms=(),
                normalized_text=normalized_text,
            )

        chosen_intent = self._choose_intent(scores)
        chosen_score = scores[chosen_intent]

        total_score = sum(scores.values())
        confidence = chosen_score / total_score if total_score else 0.0

        # Evita confiança excessiva em comandos com apenas uma palavra genérica.
        if chosen_score == 1:
            confidence = min(confidence, 0.55)

        return IntentAnalysis(
            intent=chosen_intent,
            confidence=round(confidence, 2),
            matched_terms=tuple(matches.get(chosen_intent, [])),
            normalized_text=normalized_text,
        )

    def _choose_intent(self, scores: dict[Intent, int]) -> Intent:
        """
        Escolhe a intenção de maior pontuação.

        Em caso de empate, utiliza a ordem definida em self._priority.
        """
        highest_score = max(scores.values())

        tied_intents = {
            intent
            for intent, score in scores.items()
            if score == highest_score
        }

        for intent in self._priority:
            if intent in tied_intents:
                return intent

        return next(iter(tied_intents))

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        """
        Verifica se um termo aparece como palavra ou expressão completa.
        """
        pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
        return re.search(pattern, text) is not None

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Normaliza caixa, acentos, pontuação e espaços.
        """
        normalized = str(text).strip().casefold()
        normalized = unicodedata.normalize("NFKD", normalized)
        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()