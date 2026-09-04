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

from atlas.core.config import BROWSER_CHANNEL
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

T = TypeVar("T")

_INTERACTIVE_SELECTOR = (
    "input, textarea, button, a, select, [role], "
    "[contenteditable='true'], [tabindex]"
)

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

    def get_structural_context_token(self) -> str | None:
        """Identifica a aba DOM atual sem expor URL ou conteúdo.

        O token só existe durante a execução e é usado pela Etapa 11 para
        impedir que um formulário iniciado em uma aba continue em outra.
        """

        page = self._detect_active_page()
        if page is None:
            return None
        return f"dom:{id(page)}"

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
            launch_options: dict[str, object] = {"headless": False}
            if BROWSER_CHANNEL:
                launch_options["channel"] = BROWSER_CHANNEL
            self._browser = self._playwright.chromium.launch(**launch_options)

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


    def inspect_visible_interactive_elements(
        self,
    ) -> list[dict[str, object]]:
        """Retorna elementos DOM visíveis da página Playwright ativa.

        A inspeção é somente leitura. Se o navegador do Atlas não estiver
        realmente em foco, nenhuma informação é retornada.
        """

        page = self._detect_active_page()

        if page is None:
            return []

        try:
            has_focus = bool(
                page.evaluate("document.hasFocus()")
            )
        except Exception:
            return []

        if not has_focus:
            return []

        script = r"""
        (selector) => {
            const dpr = window.devicePixelRatio || 1;
            const borderX = Math.max(
                0,
                (window.outerWidth - window.innerWidth) / 2
            );
            const chromeTop = Math.max(
                0,
                window.outerHeight - window.innerHeight - borderX
            );
            const contentLeft = window.screenX + borderX;
            const contentTop = window.screenY + chromeTop;

            const visible = (element, rect) => {
                if (rect.width < 3 || rect.height < 3) {
                    return false;
                }

                const style = window.getComputedStyle(element);

                if (
                    style.display === "none"
                    || style.visibility === "hidden"
                    || Number(style.opacity || "1") <= 0.01
                ) {
                    return false;
                }

                return (
                    rect.bottom > 0
                    && rect.right > 0
                    && rect.top < window.innerHeight
                    && rect.left < window.innerWidth
                );
            };

            return Array.from(
                document.querySelectorAll(selector)
            )
                .slice(0, 1200)
                .map((element, domIndex) => {
                    const rect = element.getBoundingClientRect();

                    if (!visible(element, rect)) {
                        return null;
                    }

                    let labels = "";

                    try {
                        if (element.labels) {
                            labels = Array.from(element.labels)
                                .map((item) => item.innerText || "")
                                .join(" ");
                        }
                    } catch (_) {
                        labels = "";
                    }

                    const text = (
                        element.innerText
                        || element.value
                        || ""
                    ).trim();

                    return {
                        dom_index: domIndex,
                        tag: (
                            element.tagName || ""
                        ).toLowerCase(),
                        role: element.getAttribute("role") || "",
                        type: element.getAttribute("type") || "",
                        name: element.getAttribute("name") || "",
                        aria_label:
                            element.getAttribute("aria-label") || "",
                        placeholder:
                            element.getAttribute("placeholder") || "",
                        title: element.getAttribute("title") || "",
                        labels,
                        text: text.slice(0, 300),
                        left: (
                            contentLeft + rect.left
                        ) * dpr,
                        top: (
                            contentTop + rect.top
                        ) * dpr,
                        right: (
                            contentLeft + rect.right
                        ) * dpr,
                        bottom: (
                            contentTop + rect.bottom
                        ) * dpr
                    };
                })
                .filter(Boolean);
        }
        """

        try:
            result = page.evaluate(
                script,
                _INTERACTIVE_SELECTOR,
            )
        except Exception:
            return []

        if not isinstance(result, list):
            return []

        return [
            item
            for item in result
            if isinstance(item, dict)
        ]

    def inspect_interaction_state(
        self,
        dom_index: int,
        *,
        fingerprint: dict[str, str] | None = None,
        semantic_kind: str = "",
    ) -> dict[str, object] | None:
        """Lê o estado da página e do alvo sem executar qualquer ação.

        A observação é usada pela Etapa 7 para comparar o estado antes e
        depois de um clique controlado. Nenhum mouse/teclado é acionado aqui.
        """

        if not isinstance(dom_index, int) or dom_index < 0:
            return None

        page = self._detect_active_page()
        if page is None:
            return None

        expected = {
            str(key): str(value or "").strip()
            for key, value in (fingerprint or {}).items()
        }

        script = r"""
        ([selector, expectedIndex, expected, semanticKind]) => {
            const elements = Array.from(
                document.querySelectorAll(selector)
            );

            const clean = (value) => (
                value == null
                    ? ""
                    : String(value)
                        .trim()
                        .replace(/\s+/g, " ")
                        .toLowerCase()
                        .slice(0, 300)
            );

            const visible = (element) => {
                if (!element) {
                    return false;
                }

                const rect = element.getBoundingClientRect();
                if (rect.width < 3 || rect.height < 3) {
                    return false;
                }

                const style = window.getComputedStyle(element);
                return (
                    style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || "1") > 0.01
                    && rect.bottom > 0
                    && rect.right > 0
                    && rect.top < window.innerHeight
                    && rect.left < window.innerWidth
                );
            };

            const snapshot = (element) => {
                if (!element) {
                    return null;
                }

                const tag = clean(
                    (element.tagName || "").toLowerCase()
                );
                const role = clean(element.getAttribute("role"));
                const value = (
                    "value" in element
                        ? clean(element.value)
                        : ""
                );

                return {
                    exists: true,
                    focused: document.activeElement === element,
                    tag,
                    role,
                    type: clean(element.getAttribute("type")),
                    name: clean(element.getAttribute("name")),
                    aria_label: clean(
                        element.getAttribute("aria-label")
                    ),
                    placeholder: clean(
                        element.getAttribute("placeholder")
                    ),
                    title: clean(element.getAttribute("title")),
                    text: clean(
                        element.innerText
                        || value
                        || ""
                    ),
                    value,
                    selected_value: (
                        tag === "select"
                            ? clean(element.value)
                            : ""
                    ),
                    selected_label: (
                        tag === "select"
                        && element.selectedOptions
                        && element.selectedOptions.length
                            ? clean(element.selectedOptions[0].textContent)
                            : ""
                    ),
                    disabled: Boolean(element.disabled),
                    checked: (
                        typeof element.checked === "boolean"
                            ? Boolean(element.checked)
                            : null
                    ),
                    aria_pressed: clean(
                        element.getAttribute("aria-pressed")
                    ),
                    aria_expanded: clean(
                        element.getAttribute("aria-expanded")
                    ),
                    aria_selected: clean(
                        element.getAttribute("aria-selected")
                    )
                };
            };

            const isTextEntry = (data) => (
                data
                && (
                    data.tag === "input"
                    || data.tag === "textarea"
                    || data.role === "searchbox"
                    || data.role === "textbox"
                    || data.role === "combobox"
                )
            );

            const resolveTarget = () => {
                if (semanticKind === "search_input") {
                    let bestIndex = -1;
                    let bestScore = -1;

                    elements.forEach((element, index) => {
                        if (!visible(element)) {
                            return;
                        }

                        const data = snapshot(element);
                        if (!isTextEntry(data)) {
                            return;
                        }

                        let score = 0;
                        if (data.role === "searchbox") score += 100;
                        if (data.name === "q") score += 95;
                        if (data.type === "search") score += 85;
                        if (data.tag === "textarea") score += 70;
                        if (data.role === "combobox") score += 65;
                        if (data.role === "textbox") score += 60;
                        if (data.tag === "input") score += 55;

                        if (
                            data.aria_label.includes("pesquis")
                            || data.aria_label.includes("search")
                            || data.aria_label.includes("busca")
                        ) {
                            score += 50;
                        }

                        if (
                            data.placeholder.includes("pesquis")
                            || data.placeholder.includes("search")
                            || data.placeholder.includes("busca")
                        ) {
                            score += 45;
                        }

                        Object.keys(expected || {}).forEach((key) => {
                            const expectedValue = clean(expected[key]);
                            if (
                                expectedValue
                                && clean(data[key]) === expectedValue
                            ) {
                                score += 6;
                            }
                        });

                        if (index === expectedIndex) {
                            score += 2;
                        }

                        if (score > bestScore) {
                            bestScore = score;
                            bestIndex = index;
                        }
                    });

                    if (bestIndex >= 0 && bestScore >= 90) {
                        return bestIndex;
                    }
                }

                const weights = {
                    aria_label: 10,
                    name: 9,
                    placeholder: 8,
                    role: 6,
                    type: 5,
                    tag: 4,
                    title: 3,
                    text: 2
                };
                const expectedKeys = Object.keys(weights)
                    .filter((key) => clean(expected[key]));

                if (!expectedKeys.length) {
                    const item = elements[expectedIndex];
                    return item && visible(item)
                        ? expectedIndex
                        : -1;
                }

                let bestIndex = -1;
                let bestScore = -1;

                elements.forEach((element, index) => {
                    if (!visible(element)) {
                        return;
                    }

                    const current = snapshot(element);
                    let score = 0;
                    let possible = 0;

                    expectedKeys.forEach((key) => {
                        const expectedValue = clean(expected[key]);
                        const currentValue = clean(current[key]);
                        const weight = weights[key];
                        possible += weight;

                        if (
                            currentValue
                            && currentValue === expectedValue
                        ) {
                            score += weight;
                        }
                    });

                    if (index === expectedIndex) {
                        score += 1;
                        possible += 1;
                    }

                    const ratio = possible > 0
                        ? score / possible
                        : 0;

                    if (ratio > bestScore) {
                        bestScore = ratio;
                        bestIndex = index;
                    }
                });

                return bestScore >= 0.62
                    ? bestIndex
                    : -1;
            };

            const targetIndex = resolveTarget();
            const target = (
                targetIndex >= 0
                    ? snapshot(elements[targetIndex])
                    : null
            );
            const active = snapshot(document.activeElement);
            const interactiveCount = elements.filter(visible).length;

            return {
                url: String(window.location.href || ""),
                title: String(document.title || ""),
                has_focus: document.hasFocus(),
                visibility_state: document.visibilityState,
                interactive_count: interactiveCount,
                dialog_count: document.querySelectorAll(
                    "[role='dialog'], dialog[open]"
                ).length,
                expanded_count: document.querySelectorAll(
                    "[aria-expanded='true']"
                ).length,
                target_index: targetIndex,
                target: target || {exists: false, focused: false},
                active: active || {exists: false, focused: false}
            };
        }
        """

        try:
            result = page.evaluate(
                script,
                [
                    _INTERACTIVE_SELECTOR,
                    dom_index,
                    expected,
                    semantic_kind,
                ],
            )
        except Exception:
            return None

        return result if isinstance(result, dict) else None

    # ==================================================
    # INTERAÇÃO
    # ==================================================



    def click_interactive_element(
        self,
        dom_index: int,
        *,
        fingerprint: dict[str, str] | None = None,
        semantic_kind: str = "",
    ) -> bool:
        """Clica um elemento DOM revalidado imediatamente antes da ação.

        A identidade textual/semântica do elemento é preferida ao índice
        original, pois páginas modernas podem recriar nós entre grounding
        e clique.
        """

        if not isinstance(dom_index, int) or dom_index < 0:
            return False

        page = self._detect_active_page()

        if page is None:
            return False

        expected = {
            str(key): str(value or "").strip()
            for key, value in (
                fingerprint or {}
            ).items()
        }

        # Foco pode oscilar por alguns milissegundos enquanto a voz/GUI
        # atualiza. Aguarda brevemente, mas nunca força foco na janela.
        focused = False

        for _ in range(4):
            try:
                focused = bool(
                    page.evaluate(
                        "document.hasFocus()"
                    )
                )
            except Exception:
                return False

            if focused:
                break

            try:
                page.wait_for_timeout(120)
            except Exception:
                return False

        if not focused:
            return False

        resolver_script = r"""
        ([selector, expectedIndex, expected, semanticKind]) => {
            const elements = Array.from(
                document.querySelectorAll(selector)
            );

            const clean = (value) => (
                value == null
                    ? ""
                    : String(value)
                        .trim()
                        .replace(/\s+/g, " ")
                        .toLowerCase()
                        .slice(0, 300)
            );

            const visible = (element) => {
                const rect = element.getBoundingClientRect();

                if (rect.width < 3 || rect.height < 3) {
                    return false;
                }

                const style = window.getComputedStyle(element);

                return (
                    style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || "1") > 0.01
                    && rect.bottom > 0
                    && rect.right > 0
                    && rect.top < window.innerHeight
                    && rect.left < window.innerWidth
                );
            };

            const snapshot = (element) => ({
                tag: clean(
                    (element.tagName || "").toLowerCase()
                ),
                role: clean(
                    element.getAttribute("role")
                ),
                type: clean(
                    element.getAttribute("type")
                ),
                name: clean(
                    element.getAttribute("name")
                ),
                aria_label: clean(
                    element.getAttribute("aria-label")
                ),
                placeholder: clean(
                    element.getAttribute("placeholder")
                ),
                title: clean(
                    element.getAttribute("title")
                ),
                text: clean(
                    element.innerText
                    || element.value
                    || ""
                )
            });

            const isTextEntry = (data) => (
                data.tag === "input"
                || data.tag === "textarea"
                || data.role === "searchbox"
                || data.role === "textbox"
                || data.role === "combobox"
            );

            if (semanticKind === "search_input") {
                let bestIndex = -1;
                let bestScore = -1;

                elements.forEach((element, index) => {
                    if (!visible(element)) {
                        return;
                    }

                    const data = snapshot(element);

                    if (!isTextEntry(data)) {
                        return;
                    }

                    let score = 0;

                    if (data.role === "searchbox") score += 100;
                    if (data.name === "q") score += 95;
                    if (data.type === "search") score += 85;
                    if (data.tag === "textarea") score += 70;
                    if (data.role === "combobox") score += 65;
                    if (data.role === "textbox") score += 60;
                    if (data.tag === "input") score += 55;

                    if (
                        data.aria_label.includes("pesquis")
                        || data.aria_label.includes("search")
                        || data.aria_label.includes("busca")
                    ) {
                        score += 50;
                    }

                    if (
                        data.placeholder.includes("pesquis")
                        || data.placeholder.includes("search")
                        || data.placeholder.includes("busca")
                    ) {
                        score += 45;
                    }

                    Object.keys(expected || {}).forEach((key) => {
                        const expectedValue = clean(expected[key]);

                        if (
                            expectedValue
                            && clean(data[key]) === expectedValue
                        ) {
                            score += 6;
                        }
                    });

                    if (index === expectedIndex) {
                        score += 2;
                    }

                    if (score > bestScore) {
                        bestScore = score;
                        bestIndex = index;
                    }
                });

                if (bestIndex >= 0 && bestScore >= 90) {
                    return bestIndex;
                }
            }

            const weights = {
                aria_label: 10,
                name: 9,
                placeholder: 8,
                role: 6,
                type: 5,
                tag: 4,
                title: 3,
                text: 2
            };

            const expectedKeys = Object.keys(weights)
                .filter((key) => clean(expected[key]));

            if (!expectedKeys.length) {
                const item = elements[expectedIndex];

                return (
                    item && visible(item)
                    ? expectedIndex
                    : -1
                );
            }

            let bestIndex = -1;
            let bestScore = -1;

            elements.forEach((element, index) => {
                if (!visible(element)) {
                    return;
                }

                const current = snapshot(element);
                let score = 0;
                let possible = 0;

                expectedKeys.forEach((key) => {
                    const expectedValue = clean(expected[key]);
                    const currentValue = clean(current[key]);
                    const weight = weights[key];

                    possible += weight;

                    if (
                        currentValue
                        && currentValue === expectedValue
                    ) {
                        score += weight;
                    }
                });

                if (index === expectedIndex) {
                    score += 1;
                    possible += 1;
                }

                const ratio = (
                    possible > 0
                        ? score / possible
                        : 0
                );

                if (ratio > bestScore) {
                    bestScore = ratio;
                    bestIndex = index;
                }
            });

            return bestScore >= 0.62
                ? bestIndex
                : -1;
        }
        """

        def resolve_index() -> int:
            try:
                resolved = page.evaluate(
                    resolver_script,
                    [
                        _INTERACTIVE_SELECTOR,
                        dom_index,
                        expected,
                        semantic_kind,
                    ],
                )
                return int(resolved)
            except (
                TypeError,
                ValueError,
                PlaywrightError,
            ):
                return -1
            except Exception:
                return -1

        # Uma segunda tentativa é permitida para DOM que se recria
        # durante animação/autocomplete, sempre revalidando identidade.
        for attempt in range(2):
            current_index = resolve_index()

            if current_index < 0:
                return False

            try:
                locator = page.locator(
                    _INTERACTIVE_SELECTOR
                ).nth(current_index)

                locator.wait_for(
                    state="visible",
                    timeout=2_500,
                )
                locator.scroll_into_view_if_needed(
                    timeout=2_500,
                )

                # Trial verifica actionability sem executar o clique.
                locator.click(
                    timeout=2_500,
                    trial=True,
                )

                locator.click(
                    timeout=4_000,
                )
                return True

            except (
                PlaywrightError,
                PlaywrightTimeoutError,
            ):
                if attempt == 0:
                    try:
                        page.wait_for_timeout(160)
                    except Exception:
                        return False
                    continue

                return False
            except Exception:
                return False

        return False

    def fill_interactive_element(
        self,
        dom_index: int,
        text: str,
        *,
        fingerprint: dict[str, str] | None = None,
        semantic_kind: str = "",
    ) -> bool:
        """Preenche um campo DOM revalidado sem usar teclado físico.

        A Etapa 10 reaproveita o resolvedor estrutural da Etapa 7: o alvo é
        reencontrado imediatamente antes do ``fill`` e campos de senha são
        recusados. Não existe fallback para coordenadas, mouse ou teclado.
        """

        if not isinstance(dom_index, int) or dom_index < 0 or not text:
            return False

        page = self._detect_active_page()
        if page is None:
            return False

        focused = False
        for _ in range(4):
            try:
                focused = bool(page.evaluate("document.hasFocus()"))
            except Exception:
                return False

            if focused:
                break

            try:
                page.wait_for_timeout(120)
            except Exception:
                return False

        if not focused:
            return False

        state = self.inspect_interaction_state(
            dom_index,
            fingerprint=fingerprint,
            semantic_kind=semantic_kind,
        )
        if not isinstance(state, dict):
            return False

        target = state.get("target")
        if not isinstance(target, dict):
            return False

        if str(target.get("type", "")).casefold() == "password":
            return False

        if bool(target.get("disabled")):
            return False

        try:
            resolved_index = int(state.get("target_index", -1))
        except (TypeError, ValueError):
            return False

        if resolved_index < 0:
            return False

        try:
            locator = page.locator(_INTERACTIVE_SELECTOR).nth(resolved_index)
            locator.wait_for(state="visible", timeout=2_500)
            locator.scroll_into_view_if_needed(timeout=2_500)
            if not locator.is_editable(timeout=2_500):
                return False
            locator.fill(text, timeout=4_000)
            return True
        except (PlaywrightError, PlaywrightTimeoutError):
            return False
        except Exception:
            return False

    def select_interactive_option(
        self,
        dom_index: int,
        option: str,
        *,
        fingerprint: dict[str, str] | None = None,
        semantic_kind: str = "",
    ) -> bool:
        """Seleciona uma opção de ``<select>`` DOM revalidado.

        A Etapa 12 não simula mouse/teclado. O alvo precisa continuar
        estruturalmente identificável e ser um ``select`` nativo visível e
        habilitado. A seleção tenta label e value explicitamente.
        """

        if not isinstance(dom_index, int) or dom_index < 0 or not option.strip():
            return False

        page = self._detect_active_page()
        if page is None:
            return False

        state = self.inspect_interaction_state(
            dom_index,
            fingerprint=fingerprint,
            semantic_kind=semantic_kind,
        )
        if not isinstance(state, dict):
            return False

        target = state.get("target")
        if not isinstance(target, dict):
            return False

        if str(target.get("tag", "")).casefold() != "select":
            return False

        if bool(target.get("disabled")):
            return False

        try:
            resolved_index = int(state.get("target_index", -1))
        except (TypeError, ValueError):
            return False

        if resolved_index < 0:
            return False

        locator = page.locator(_INTERACTIVE_SELECTOR).nth(resolved_index)
        requested = option.strip()

        try:
            locator.wait_for(state="visible", timeout=2_500)
            locator.scroll_into_view_if_needed(timeout=2_500)

            try:
                selected = locator.select_option(
                    label=requested,
                    timeout=3_500,
                )
            except (PlaywrightError, PlaywrightTimeoutError):
                selected = locator.select_option(
                    value=requested,
                    timeout=3_500,
                )

            return bool(selected)
        except (PlaywrightError, PlaywrightTimeoutError):
            return False
        except Exception:
            return False

    def set_interactive_control_state(
        self,
        dom_index: int,
        desired_state: bool,
        *,
        fingerprint: dict[str, str] | None = None,
        semantic_kind: str = "",
    ) -> bool:
        """Altera checkbox/radio/switch por estado estrutural.

        A Etapa 13 usa ``set_checked`` do Playwright. O método recusa controles
        genéricos, desabilitados e a tentativa de desmarcar radio buttons. Não
        existe fallback por coordenada, mouse físico ou teclado.
        """

        if not isinstance(dom_index, int) or dom_index < 0:
            return False

        page = self._detect_active_page()
        if page is None:
            return False

        state = self.inspect_interaction_state(
            dom_index,
            fingerprint=fingerprint,
            semantic_kind=semantic_kind,
        )
        if not isinstance(state, dict):
            return False

        target = state.get("target")
        if not isinstance(target, dict) or bool(target.get("disabled")):
            return False

        tag = str(target.get("tag", "")).casefold()
        role = str(target.get("role", "")).casefold()
        input_type = str(target.get("type", "")).casefold()
        is_checkbox = input_type == "checkbox" or role in {"checkbox", "switch"}
        is_radio = input_type == "radio" or role == "radio"

        if not (is_checkbox or is_radio):
            return False
        if is_radio and not desired_state:
            return False
        if tag not in {"input", "button", "div", "span"} and not role:
            return False

        current_state = target.get("checked")
        if isinstance(current_state, bool) and current_state is desired_state:
            return True

        try:
            resolved_index = int(state.get("target_index", -1))
        except (TypeError, ValueError):
            return False
        if resolved_index < 0:
            return False

        try:
            locator = page.locator(_INTERACTIVE_SELECTOR).nth(resolved_index)
            locator.wait_for(state="visible", timeout=2_500)
            locator.scroll_into_view_if_needed(timeout=2_500)
            locator.set_checked(desired_state, timeout=4_000)
            return True
        except (PlaywrightError, PlaywrightTimeoutError):
            return False
        except Exception:
            return False

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

    def activate_final_control(
        self,
        dom_index: int,
        *,
        fingerprint: dict[str, str] | None = None,
        semantic_kind: str = "button",
    ) -> bool:
        """Ativa somente um botão final estrutural previamente confirmado.

        O uso é restrito à Etapa 14, depois da confirmação humana de uso único.
        O alvo é revalidado e precisa continuar sendo um botão de envio.
        """

        page = self._detect_active_page()
        if page is None or not isinstance(dom_index, int) or dom_index < 0:
            return False

        state = self.inspect_interaction_state(
            dom_index,
            fingerprint=fingerprint,
            semantic_kind=semantic_kind,
        )
        if not isinstance(state, dict):
            return False

        target = state.get("target")
        if not isinstance(target, dict) or bool(target.get("disabled")):
            return False

        tag = str(target.get("tag", "")).casefold()
        role = str(target.get("role", "")).casefold()
        input_type = str(target.get("type", "")).casefold()
        identity = " ".join(
            str(target.get(key, "")).casefold()
            for key in ("text", "aria_label", "name", "title")
        )
        final_terms = {"enviar", "submit", "confirmar"}
        is_button = (
            tag == "button"
            or role == "button"
            or (tag == "input" and input_type in {"button", "submit"})
        )
        if not is_button or not any(term in identity for term in final_terms):
            return False

        try:
            resolved_index = int(state.get("target_index", -1))
        except (TypeError, ValueError):
            return False
        if resolved_index < 0:
            return False

        try:
            locator = page.locator(_INTERACTIVE_SELECTOR).nth(resolved_index)
            locator.wait_for(state="visible", timeout=2_500)
            locator.scroll_into_view_if_needed(timeout=2_500)
            locator.click(timeout=2_500, trial=True)
            locator.click(timeout=4_000)
            return True
        except (PlaywrightError, PlaywrightTimeoutError):
            return False
        except Exception:
            return False

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
