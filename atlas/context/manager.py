from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from atlas.browser.session import BrowserSession
from atlas.session.manager import SessionManager


@dataclass
class ConversationTurn:
    user_message: str
    atlas_response: str
    created_at: datetime


class ContextManager:
    """
    Centraliza o contexto temporário e persistente do Atlas.

    Responsabilidades:
    - Histórico recente da conversa
    - Último comando e última resposta
    - Último tópico e última pesquisa
    - Contexto persistente do projeto
    - Contexto das abas do navegador
    """

    def __init__(self, max_turns: int = 10) -> None:
        self.history: deque[ConversationTurn] = deque(
            maxlen=max_turns
        )

        # Contexto temporário da conversa
        self.last_command: str | None = None
        self.last_response: str | None = None
        self.last_topic: str | None = None
        self.last_opened_target: str | None = None
        self.last_search: str | None = None
        self.current_goal: str | None = None

        # Gerenciadores especializados
        self.session = SessionManager()
        self.browser = BrowserSession()

    # ======================================================
    # CONVERSA
    # ======================================================

    def add_turn(
        self,
        user_message: str,
        atlas_response: str,
    ) -> None:
        turn = ConversationTurn(
            user_message=user_message,
            atlas_response=atlas_response,
            created_at=datetime.now(),
        )

        self.history.append(turn)

        self.last_command = user_message
        self.last_response = atlas_response

    def get_recent_history(self) -> str:
        if not self.history:
            return ""

        lines: list[str] = []

        for item in self.history:
            lines.append(
                f"Usuário: {item.user_message}"
            )
            lines.append(
                f"Atlas: {item.atlas_response}"
            )

        return "\n".join(lines)

    # ======================================================
    # CONTEXTO TEMPORÁRIO
    # ======================================================

    def remember_topic(self, topic: str) -> None:
        topic = topic.strip()

        if topic:
            self.last_topic = topic

    def remember_search(self, search: str) -> None:
        search = search.strip()

        if not search:
            return

        self.last_search = search
        self.last_topic = search

    def remember_opened_target(self, target: str) -> None:
        target = target.strip()

        if target:
            self.last_opened_target = target

    def remember_goal(self, goal: str) -> None:
        goal = goal.strip()

        if goal:
            self.current_goal = goal

    # ======================================================
    # ACESSO AOS GERENCIADORES
    # ======================================================

    def get_session_manager(self) -> SessionManager:
        return self.session

    def get_browser_session(self) -> BrowserSession:
        return self.browser

    # ======================================================
    # CONTEXTO ESTRUTURADO
    # ======================================================

    def get_context(self) -> dict:
        return {
            "last_command": self.last_command,
            "last_response": self.last_response,
            "last_topic": self.last_topic,
            "last_search": self.last_search,
            "last_opened_target": self.last_opened_target,
            "current_goal": self.current_goal,
            "history": self.get_recent_history(),
            "session": self.session.load(),
            "browser": self.browser.build_context(),
        }

    # ======================================================
    # CONTEXTO PARA O CÉREBRO
    # ======================================================

    def build_prompt_context(self) -> str:
        sections: list[str] = []

        conversation_context = self._build_conversation_context()

        if conversation_context:
            sections.append(conversation_context)

        try:
            session_context = (
                self.session.build_prompt_context()
            )

            if session_context:
                sections.append(session_context)

        except Exception as error:
            sections.append(
                "Não foi possível carregar o contexto "
                f"persistente da sessão: {error}"
            )

        try:
            browser_context = self.browser.build_context()

            if browser_context:
                sections.append(browser_context)

        except Exception as error:
            sections.append(
                "Não foi possível carregar o contexto "
                f"do navegador: {error}"
            )

        if not sections:
            return "Nenhum contexto disponível."

        return "\n\n".join(sections)

    def _build_conversation_context(self) -> str:
        lines: list[str] = []

        if self.current_goal:
            lines.append(
                f"- Objetivo atual: {self.current_goal}"
            )

        if self.last_topic:
            lines.append(
                f"- Último tópico: {self.last_topic}"
            )

        if self.last_search:
            lines.append(
                f"- Última pesquisa: {self.last_search}"
            )

        if self.last_opened_target:
            lines.append(
                "- Último alvo aberto: "
                f"{self.last_opened_target}"
            )

        if self.last_command:
            lines.append(
                f"- Último comando: {self.last_command}"
            )

        recent_history = self.get_recent_history()

        if recent_history:
            lines.append(
                "\nHistórico recente da conversa:\n"
                f"{recent_history}"
            )

        if not lines:
            return ""

        return (
            "Contexto temporário do Atlas:\n"
            + "\n".join(lines)
        )

    # ======================================================
    # LIMPEZA
    # ======================================================

    def clear_conversation(self) -> None:
        """
        Limpa somente o contexto temporário.

        A sessão persistente do projeto não é apagada.
        """

        self.history.clear()

        self.last_command = None
        self.last_response = None
        self.last_topic = None
        self.last_opened_target = None
        self.last_search = None
        self.current_goal = None

    def clear_browser(self) -> None:
        self.browser.clear()

    def clear_all_context(self) -> None:
        """
        Limpa conversa e navegador.

        Não apaga automaticamente o arquivo da sessão
        persistente para evitar perda acidental.
        """

        self.clear_conversation()
        self.clear_browser()

    def clear(self) -> None:
        """
        Mantém compatibilidade com o código antigo.
        """

        self.clear_conversation()