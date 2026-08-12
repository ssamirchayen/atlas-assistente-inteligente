from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

T = TypeVar("T")

if TYPE_CHECKING:
    from atlas.browser.session import BrowserSession


class BrowserAutomation:
    """
    Automação de navegador do Atlas usando Playwright.

    Mantém uma única sessão aberta e recria automaticamente o navegador
    quando a página, o contexto ou o Chromium forem fechados.
    """

    def __init__(
        self,
        session: BrowserSession | None = None,
    ) -> None:
        self._session = session
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._current_page: Page | None = None
        self._last_search_page: Page | None = None
        self._last_search_url: str | None = None

    @staticmethod
    def _tab_id(page: Page) -> str:
        return f"playwright-{id(page)}"

    def _remember_page(
        self,
        page: Page,
        *,
        tab_type: str = "generic",
        search_query: str = "",
    ) -> None:
        """Mantém o contexto conversacional alinhado ao Playwright."""

        if self._session is None:
            return

        try:
            title = page.title()
        except Exception:
            title = ""

        try:
            url = page.url
        except Exception:
            url = ""

        self._session.register_tab(
            tab_id=self._tab_id(page),
            url=url,
            title=title,
            tab_type=tab_type,
            search_query=search_query,
        )

    # ==================================================
    # CICLO DE VIDA
    # ==================================================

    def _reset_browser(self) -> None:
        """Descarta referências antigas ou fechadas sem gerar erro."""

        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass

        try:
            if self._browser is not None and self._browser.is_connected():
                self._browser.close()
        except Exception:
            pass

        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass

        self._page = None
        self._current_page = None
        self._last_search_page = None
        self._last_search_url = None
        self._context = None
        self._browser = None
        self._playwright = None

        if self._session is not None:
            self._session.clear()

    def _get_open_pages(self) -> list[Page]:
        """Retorna somente as páginas abertas e ainda acessíveis."""

        if self._context is None:
            return []

        open_pages: list[Page] = []

        for page in self._context.pages:
            try:
                if page.is_closed():
                    continue

                # Confirma que o canal do Playwright ainda responde.
                _ = page.url
                open_pages.append(page)
            except Exception:
                continue

        return open_pages

    def _detect_active_page(self) -> Page | None:
        """
        Detecta a aba selecionada pelo usuário no Chromium.

        O Playwright não oferece uma propriedade direta de "aba ativa".
        Por isso, verificamos o estado de visibilidade de cada página. A aba
        atualmente selecionada normalmente retorna ``visible`` enquanto as
        demais retornam ``hidden``.
        """

        open_pages = self._get_open_pages()

        if not open_pages:
            return None

        for page in reversed(open_pages):
            try:
                visibility_state = page.evaluate(
                    "document.visibilityState"
                )

                if visibility_state == "visible":
                    return page
            except Exception:
                continue

        # Fallback seguro para páginas em que JavaScript não pode ser avaliado.
        for candidate in (
            self._current_page,
            self._page,
            self._last_search_page,
        ):
            if candidate in open_pages:
                return candidate

        return open_pages[-1]

    def _synchronize_current_page(self) -> Page | None:
        """Atualiza as referências internas para a aba ativa real."""

        page = self._detect_active_page()

        if page is None:
            self._page = None
            self._current_page = None
            return None

        self._page = page
        self._current_page = page
        self._remember_page(page)
        return page

    def _ensure_browser(self) -> Page:
        """
        Retorna uma página válida e sincronizada com a aba ativa.

        Se o usuário trocar de aba manualmente, a referência interna é
        atualizada antes de cada ação. Se o Chromium ou o contexto forem
        fechados, o navegador é recriado automaticamente.
        """

        try:
            if self._browser is not None and not self._browser.is_connected():
                self._reset_browser()
        except Exception:
            self._reset_browser()

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        if self._browser is None:
            self._browser = self._playwright.chromium.launch(
                headless=False,
            )

        if self._context is None:
            self._context = self._browser.new_context(
                viewport={
                    "width": 1366,
                    "height": 768,
                },
                locale="pt-BR",
            )

        page = self._synchronize_current_page()

        if page is None:
            page = self._context.new_page()
            self._page = page
            self._current_page = page

        return page

    def _activate_page(self, page: Page) -> Page:
        """Ativa uma página válida e a define como página de trabalho."""

        if page.is_closed():
            raise RuntimeError("A página selecionada foi fechada.")

        page.bring_to_front()
        self._page = page
        self._current_page = page
        self._remember_page(page)
        return page

    def _get_last_search_page(self) -> Page:
        """Recupera a última pesquisa e restaura sua URL quando necessário."""

        page = self._last_search_page
        open_pages = self._get_open_pages()

        if page not in open_pages:
            page = next(
                (
                    candidate
                    for candidate in open_pages
                    if self._last_search_url
                    and candidate.url == self._last_search_url
                ),
                None,
            )

        if page is None:
            page = self._ensure_browser()
            self._last_search_page = page

        page = self._activate_page(page)

        if self._last_search_url and page.url != self._last_search_url:
            page.goto(
                self._last_search_url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

        self._last_search_page = page
        self._remember_page(page, tab_type="google_search")

        return page

    def _run_with_recovery(
        self,
        operation: Callable[[Page], T],
    ) -> T:
        """
        Executa uma operação e tenta novamente uma vez quando o alvo fechou.
        """

        try:
            return operation(self._ensure_browser())

        except PlaywrightError as error:
            message = str(error).lower()

            target_closed = any(
                text in message
                for text in (
                    "target page, context or browser has been closed",
                    "target closed",
                    "browser has been closed",
                    "page has been closed",
                    "context has been closed",
                )
            )

            if not target_closed:
                raise

            last_search_url = self._last_search_url
            self._reset_browser()
            self._last_search_url = last_search_url
            return operation(self._ensure_browser())

    # ==================================================
    # NAVEGAÇÃO
    # ==================================================

    def open_url(self, url: str) -> str:
        url = url.strip()

        if not url:
            return "Nenhum endereço foi informado."

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        def operation(page: Page) -> None:
            self._activate_page(page)
            self._last_search_page = page
            self._last_search_url = url
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            self._activate_page(page)

        try:
            self._run_with_recovery(operation)
            return f"Abri o endereço: {url}"

        except PlaywrightTimeoutError:
            return (
                "O endereço demorou para carregar, "
                f"mas o navegador foi direcionado para: {url}"
            )

        except Exception as error:
            return f"Erro ao abrir o endereço: {error}"

    def open_named_site(self, name: str) -> str:
        normalized_name = name.strip().lower()

        sites = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "whatsapp": "https://web.whatsapp.com",
            "whatsapp web": "https://web.whatsapp.com",
            "gmail": "https://mail.google.com",
            "chatgpt": "https://chatgpt.com",
            "github": "https://github.com",
            "linkedin": "https://www.linkedin.com",
            "instagram": "https://www.instagram.com",
            "facebook": "https://www.facebook.com",
        }

        url = sites.get(normalized_name)

        if url is None:
            return f"Site não cadastrado: {name}"

        return self.open_url(url)

    # ==================================================
    # PESQUISAS
    # ==================================================

    def search_google(self, query: str) -> str:
        query = query.strip()

        if not query:
            return "Nenhuma pesquisa foi informada."

        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}"

        def operation(page: Page) -> None:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            self._activate_page(page)
            self._remember_page(
                page,
                tab_type="google_search",
                search_query=query,
            )

        try:
            self._run_with_recovery(operation)
            return f"Pesquisei no Google por: {query}"

        except PlaywrightTimeoutError:
            return (
                "A pesquisa demorou para carregar, "
                f"mas foi enviada ao Google: {query}"
            )

        except Exception as error:
            return f"Erro ao pesquisar no Google: {error}"

    def search_youtube(self, query: str) -> str:
        query = query.strip()

        if not query:
            return "Nenhuma pesquisa foi informada."

        encoded_query = urllib.parse.quote_plus(query)
        url = (
            "https://www.youtube.com/results"
            f"?search_query={encoded_query}"
        )

        def operation(page: Page) -> None:
            self._activate_page(page)
            self._last_search_page = page
            self._last_search_url = url
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            self._activate_page(page)
            self._remember_page(
                page,
                tab_type="youtube_search",
                search_query=query,
            )

        try:
            self._run_with_recovery(operation)
            return f"Pesquisei no YouTube por: {query}"

        except PlaywrightTimeoutError:
            return (
                "A pesquisa demorou para carregar, "
                f"mas foi enviada ao YouTube: {query}"
            )

        except Exception as error:
            return f"Erro ao pesquisar no YouTube: {error}"

    # ==================================================
    # RESULTADOS DO GOOGLE
    # ==================================================

    def click_first_result(self) -> str:
        return self._click_google_result(
            index=0,
            position_name="primeiro",
        )

    def click_second_result(self) -> str:
        return self._click_google_result(
            index=1,
            position_name="segundo",
        )

    def _click_google_result(
        self,
        index: int,
        position_name: str,
    ) -> str:
        def operation(_: Page) -> str:
            page = self._get_last_search_page()
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=15_000,
            )

            result_links = page.locator(
                "#search a:has(h3), a:has(h3)"
            )
            selected_result = result_links.nth(index)

            # O DOMContentLoaded pode ocorrer antes de o Google montar os
            # cartões de resultado. Aguardamos o item solicitado aparecer.
            selected_result.wait_for(
                state="visible",
                timeout=15_000,
            )

            title = selected_result.locator("h3").inner_text(
                timeout=5_000,
            )

            pages_before = self._get_open_pages()
            selected_result.click(timeout=15_000)

            try:
                page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=15_000,
                )
            except PlaywrightTimeoutError:
                pass

            open_pages = self._get_open_pages()
            new_pages = [
                candidate
                for candidate in open_pages
                if candidate not in pages_before
            ]
            destination = new_pages[-1] if new_pages else page
            self._activate_page(destination)

            return (
                f"Cliquei no {position_name} resultado: "
                f"{title}"
            )

        try:
            return self._run_with_recovery(operation)

        except PlaywrightTimeoutError:
            return (
                f"O {position_name} resultado demorou "
                "para ficar disponível."
            )

        except Exception as error:
            return (
                f"Erro ao clicar no {position_name} "
                f"resultado: {error}"
            )

    # ==================================================
    # INTERAÇÃO
    # ==================================================

    def click_text(self, text: str) -> str:
        text = text.strip()

        if not text:
            return "Nenhum texto foi informado para o clique."

        def operation(page: Page) -> None:
            locator = page.get_by_text(text, exact=False).first
            locator.wait_for(state="visible", timeout=15_000)
            locator.click(timeout=15_000)

        try:
            self._run_with_recovery(operation)
            return f"Cliquei no texto: {text}"

        except PlaywrightTimeoutError:
            return f"Não encontrei um elemento com o texto: {text}"

        except Exception as error:
            return f"Erro ao clicar no texto '{text}': {error}"

    def fill_input(
        self,
        selector: str,
        text: str,
    ) -> str:
        selector = selector.strip()
        text = text.strip()

        if not selector:
            return "Nenhum seletor foi informado."

        if not text:
            return "Nenhum texto foi informado."

        def operation(page: Page) -> None:
            field = page.locator(selector).first
            field.wait_for(state="visible", timeout=15_000)
            field.fill(text)

        try:
            self._run_with_recovery(operation)
            return "Campo preenchido com sucesso."

        except PlaywrightTimeoutError:
            return (
                "Não encontrei o campo solicitado "
                f"com o seletor: {selector}"
            )

        except Exception as error:
            return f"Erro ao preencher o campo: {error}"

    def press_key(self, key: str) -> str:
        key = key.strip()

        if not key:
            return "Nenhuma tecla foi informada."

        key_aliases = {
            "enter": "Enter",
            "entrada": "Enter",
            "esc": "Escape",
            "escape": "Escape",
            "tab": "Tab",
            "espaco": "Space",
            "espaço": "Space",
            "backspace": "Backspace",
        }

        playwright_key = key_aliases.get(key.lower(), key)

        def operation(page: Page) -> None:
            page.keyboard.press(playwright_key)

        try:
            self._run_with_recovery(operation)
            return f"Pressionei a tecla: {playwright_key}"

        except Exception as error:
            return f"Erro ao pressionar a tecla: {error}"

    # ==================================================
    # INFORMAÇÕES E ESPERA
    # ==================================================

    def wait_page(self, seconds: float = 2.0) -> str:
        try:
            seconds = float(seconds)

            if seconds < 0:
                return "O tempo de espera não pode ser negativo."

            def operation(page: Page) -> None:
                page.wait_for_timeout(seconds * 1_000)

            self._run_with_recovery(operation)
            return f"Aguardei {seconds:g} segundos na página."

        except Exception as error:
            return f"Erro ao aguardar a página: {error}"

    def get_current_url(self) -> str:
        try:
            url = self._run_with_recovery(lambda page: page.url)
            return f"Endereço atual: {url}"

        except Exception as error:
            return f"Erro ao obter o endereço atual: {error}"

    def get_page_title(self) -> str:
        try:
            title = self._run_with_recovery(lambda page: page.title())

            if not title:
                return "A página atual não possui título."

            return f"Título da página: {title}"

        except Exception as error:
            return f"Erro ao obter o título da página: {error}"

    def close(self) -> str:
        self._reset_browser()
        return "Navegador encerrado."
