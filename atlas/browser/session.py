from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BrowserTab:
    tab_id: str
    url: str = ""
    title: str = ""
    tab_type: str = "generic"
    search_query: str = ""
    last_used_at: str = field(
        default_factory=lambda: datetime.now().isoformat(
            timespec="seconds"
        )
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_used_at = datetime.now().isoformat(
            timespec="seconds"
        )


class BrowserSession:
    """
    Mantém o contexto de navegação do Atlas.

    Esta classe não controla o Playwright diretamente.
    Ela apenas registra informações sobre abas,
    pesquisas, URLs e histórico recente.
    """

    def __init__(self) -> None:
        self._tabs: dict[str, BrowserTab] = {}
        self._current_tab_id: str | None = None
        self._previous_tab_id: str | None = None
        self._last_search_tab_id: str | None = None
        self._history: list[str] = []

    def register_tab(
        self,
        tab_id: str,
        url: str = "",
        title: str = "",
        tab_type: str = "generic",
        search_query: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> BrowserTab:
        tab_id = tab_id.strip()

        if not tab_id:
            raise ValueError("O identificador da aba não pode ser vazio.")

        tab = self._tabs.get(tab_id)

        if tab is None:
            tab = BrowserTab(
                tab_id=tab_id,
                url=url,
                title=title,
                tab_type=tab_type,
                search_query=search_query,
                metadata=metadata or {},
            )

            self._tabs[tab_id] = tab

        else:
            if url:
                tab.url = url

            if title:
                tab.title = title

            if tab_type:
                tab.tab_type = tab_type

            if search_query:
                tab.search_query = search_query

            if metadata:
                tab.metadata.update(metadata)

            tab.touch()

        self.set_current_tab(tab_id)

        if tab_type in {
            "google_search",
            "youtube_search",
            "search",
        }:
            self._last_search_tab_id = tab_id

        self._append_history(tab_id)

        return tab

    def update_tab(
        self,
        tab_id: str,
        url: str | None = None,
        title: str | None = None,
        tab_type: str | None = None,
        search_query: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BrowserTab | None:
        tab = self._tabs.get(tab_id)

        if tab is None:
            return None

        if url is not None:
            tab.url = url

        if title is not None:
            tab.title = title

        if tab_type is not None:
            tab.tab_type = tab_type

        if search_query is not None:
            tab.search_query = search_query

        if metadata:
            tab.metadata.update(metadata)

        tab.touch()
        self._append_history(tab_id)

        return tab

    def set_current_tab(self, tab_id: str) -> bool:
        if tab_id not in self._tabs:
            return False

        if self._current_tab_id != tab_id:
            self._previous_tab_id = self._current_tab_id
            self._current_tab_id = tab_id

        self._tabs[tab_id].touch()
        self._append_history(tab_id)

        return True

    def set_last_search_tab(self, tab_id: str) -> bool:
        if tab_id not in self._tabs:
            return False

        self._last_search_tab_id = tab_id
        self._tabs[tab_id].touch()

        return True

    def remove_tab(self, tab_id: str) -> bool:
        if tab_id not in self._tabs:
            return False

        del self._tabs[tab_id]

        if self._current_tab_id == tab_id:
            self._current_tab_id = None

        if self._previous_tab_id == tab_id:
            self._previous_tab_id = None

        if self._last_search_tab_id == tab_id:
            self._last_search_tab_id = None

        self._history = [
            history_id
            for history_id in self._history
            if history_id != tab_id
        ]

        return True

    def clear(self) -> None:
        self._tabs.clear()
        self._current_tab_id = None
        self._previous_tab_id = None
        self._last_search_tab_id = None
        self._history.clear()

    def get_tab(self, tab_id: str) -> BrowserTab | None:
        return self._tabs.get(tab_id)

    def get_current_tab(self) -> BrowserTab | None:
        if self._current_tab_id is None:
            return None

        return self._tabs.get(self._current_tab_id)

    def get_previous_tab(self) -> BrowserTab | None:
        if self._previous_tab_id is None:
            return None

        return self._tabs.get(self._previous_tab_id)

    def get_last_search_tab(self) -> BrowserTab | None:
        if self._last_search_tab_id is None:
            return None

        return self._tabs.get(self._last_search_tab_id)

    def get_tabs(self) -> list[BrowserTab]:
        return list(self._tabs.values())

    def get_recent_tabs(
        self,
        limit: int = 10,
    ) -> list[BrowserTab]:
        if limit <= 0:
            return []

        recent_ids = list(reversed(self._history))
        unique_ids: list[str] = []

        for tab_id in recent_ids:
            if tab_id not in unique_ids:
                unique_ids.append(tab_id)

            if len(unique_ids) >= limit:
                break

        return [
            self._tabs[tab_id]
            for tab_id in unique_ids
            if tab_id in self._tabs
        ]

    def find_tab(
        self,
        text: str,
    ) -> BrowserTab | None:
        normalized_text = text.strip().lower()

        if not normalized_text:
            return None

        candidates = self.get_recent_tabs(
            limit=len(self._tabs)
        )

        for tab in candidates:
            searchable_content = " ".join(
                [
                    tab.title,
                    tab.url,
                    tab.tab_type,
                    tab.search_query,
                ]
            ).lower()

            if normalized_text in searchable_content:
                return tab

        return None

    def build_context(self) -> str:
        if not self._tabs:
            return "Nenhuma sessão de navegador ativa."

        lines = ["Contexto atual do navegador:"]

        current_tab = self.get_current_tab()

        if current_tab is not None:
            lines.append(
                f"- Aba atual: {self._describe_tab(current_tab)}"
            )

        previous_tab = self.get_previous_tab()

        if previous_tab is not None:
            lines.append(
                f"- Aba anterior: {self._describe_tab(previous_tab)}"
            )

        last_search_tab = self.get_last_search_tab()

        if last_search_tab is not None:
            lines.append(
                "- Última pesquisa: "
                f"{self._describe_tab(last_search_tab)}"
            )

        recent_tabs = self.get_recent_tabs(limit=5)

        if recent_tabs:
            lines.append("- Abas recentes:")

            for tab in recent_tabs:
                lines.append(
                    f"  • {self._describe_tab(tab)}"
                )

        return "\n".join(lines)

    def _append_history(self, tab_id: str) -> None:
        self._history.append(tab_id)

        if len(self._history) > 100:
            self._history = self._history[-100:]

    @staticmethod
    def _describe_tab(tab: BrowserTab) -> str:
        parts: list[str] = []

        if tab.title:
            parts.append(tab.title)

        if tab.search_query:
            parts.append(
                f"pesquisa: {tab.search_query}"
            )

        if tab.url:
            parts.append(tab.url)

        if not parts:
            parts.append(tab.tab_id)

        return " | ".join(parts)