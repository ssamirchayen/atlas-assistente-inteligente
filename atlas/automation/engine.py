from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from atlas.automation.browser import BrowserAutomation
from atlas.automation.domains import DomainAutomation
from atlas.automation.files import FileAutomation
from atlas.automation.helpdesk import HelpDeskAutomation
from atlas.automation.hr import HRAutomation
from atlas.automation.keyboard import KeyboardAutomation
from atlas.automation.mouse import MouseAutomation
from atlas.automation.process import ProcessAutomation
from atlas.automation.sales import SalesAutomation
from atlas.automation.window import WindowAutomation
from atlas.browser.session import BrowserSession
from atlas.connectors import ConnectorPrincipal
from atlas.internet import (
    SearchFreshness,
    WebSearchRequest,
    WebSearchService,
    build_default_web_search_service,
    build_local_search_principal,
)
from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult

logger = logging.getLogger(__name__)


class AutomationEngine:
    def __init__(
        self,
        browser_session: BrowserSession | None = None,
        internet_search: WebSearchService | None = None,
        internet_principal: ConnectorPrincipal | None = None,
        domain_responder: Callable[[str], str] | None = None,
    ) -> None:
        self.browser = BrowserAutomation(browser_session)
        self.domains = DomainAutomation(domain_responder)
        self.files = FileAutomation()
        self.helpdesk = HelpDeskAutomation()
        self.hr = HRAutomation()
        self.keyboard = KeyboardAutomation()
        self.mouse = MouseAutomation()
        self.process = ProcessAutomation()
        self.sales = SalesAutomation()
        self.window = WindowAutomation()
        self.internet_search = (
            internet_search or build_default_web_search_service()
        )
        self.internet_principal = (
            internet_principal or build_local_search_principal()
        )

        self._handlers: dict[
            str,
            Callable[[dict[str, Any]], str],
        ] = {
            # Teclado
            "keyboard.write": self._keyboard_write,
            "keyboard.press": self._keyboard_press,

            # Mouse
            "mouse.click": self._mouse_click,

            # Processos
            "process.start": self._process_start,

            # Suporte de TI
            "helpdesk.diagnose": self._helpdesk_diagnose,

            # Recursos Humanos
            "hr.generate_document": self._hr_generate_document,

            # Comercial
            "sales.compose_message": self._sales_compose_message,

            # Agentes consultivos de domínio
            "domain.programming_assist": self._domain_programming_assist,
            "domain.radiology_support": self._domain_radiology_support,
            "domain.wholesale_analysis": self._domain_wholesale_analysis,
            "domain.industry_analysis": self._domain_industry_analysis,

            # Pesquisa mult fonte
            "internet.search": self._internet_search,

            # Navegador
            "browser.open": self._browser_open,
            "browser.open_site": self._browser_open_site,
            "browser.search": self._browser_search,
            "browser.youtube_search": (
                self._browser_youtube_search
            ),
            "browser.click_first_result": (
                self._browser_click_first_result
            ),
            "browser.click_second_result": (
                self._browser_click_second_result
            ),
            "browser.click_text": self._browser_click_text,
            "browser.fill_input": self._browser_fill_input,
            "browser.press_key": self._browser_press_key,
            "browser.wait_page": self._browser_wait_page,
            "browser.current_url": self._browser_current_url,
            "browser.page_title": self._browser_page_title,
            "browser.close": self._browser_close,

            # Arquivos
            "file.create_folder": self._file_create_folder,
            "file.create_file": self._file_create_file,
            "file.delete": self._file_delete,
            "file.copy": self._file_copy,
            "file.move": self._file_move,
            "file.rename": self._file_rename,

            # Janelas
            "window.minimize": self._window_minimize,
            "window.maximize": self._window_maximize,
            "window.restore": self._window_restore,
            "window.close": self._window_close,
            "window.next": self._window_next,
            "window.previous": self._window_previous,
            "window.desktop": self._window_desktop,
            "window.focus": self._window_focus,
            "window.minimize_title": (
                self._window_minimize_title
            ),
            "window.maximize_title": (
                self._window_maximize_title
            ),
            "window.close_title": (
                self._window_close_title
            ),

            # Sistema
            "system.wait": self._system_wait,
        }

    def execute(
        self,
        action: Action,
    ) -> ExecutionResult:
        """Executa uma única ação criada pelo planner."""

        action_type = action.type
        parameters = action.parameters or {}

        logger.debug(
            "AutomationEngine recebeu ação '%s' "
            "com parâmetros %s.",
            action_type,
            parameters,
        )

        handler = self._handlers.get(action_type)

        if handler is None:
            return ExecutionResult.fail(
                action_type,
                f"Ação desconhecida: {action_type}",
                error_code="unknown_action",
            )

        started_at = time.perf_counter()

        try:
            message = handler(parameters)

            duration = (
                time.perf_counter()
                - started_at
            )

            if self._message_indicates_failure(
                message
            ):
                return ExecutionResult.fail(
                    action_type,
                    message,
                    error_code="automation_failed",
                    retryable=(
                        self._message_indicates_retry(
                            message
                        )
                    ),
                    duration=duration,
                )

            return ExecutionResult.ok(
                action_type,
                message,
                duration=duration,
            )

        except KeyError as error:
            missing_parameter = error.args[0]

            return ExecutionResult.fail(
                action_type,
                (
                    "Parâmetro obrigatório ausente "
                    "na ação "
                    f"'{action_type}': "
                    f"{missing_parameter}"
                ),
                error_code="missing_parameter",
                duration=(
                    time.perf_counter()
                    - started_at
                ),
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            return ExecutionResult.fail(
                action_type,
                (
                    "Parâmetro inválido na ação "
                    f"'{action_type}': {error}"
                ),
                error_code="invalid_parameter",
                duration=(
                    time.perf_counter()
                    - started_at
                ),
            )

        except Exception as error:
            logger.exception(
                "Falha ao executar a ação '%s'.",
                action_type,
            )

            return ExecutionResult.fail(
                action_type,
                (
                    "Erro ao executar a ação "
                    f"'{action_type}': {error}"
                ),
                error_code="unexpected_error",
                retryable=True,
                duration=(
                    time.perf_counter()
                    - started_at
                ),
            )


    def close(self) -> None:
        """Encerra com segurança os recursos mantidos pela automação."""

        try:
            self.browser.close()
        except Exception:
            logger.exception(
                "Erro ao encerrar BrowserAutomation."
            )

    @staticmethod
    def _message_indicates_failure(
        message: str,
    ) -> bool:
        normalized = (
            message
            .strip()
            .casefold()
        )

        failure_prefixes = (
            "erro",
            "não ",
            "nenhum ",
            "nenhuma ",
            "site não cadastrado",
            "arquivo ou pasta não encontrado",
            "o tempo de espera não pode",
            "você precisa informar",
            "parâmetro",
            "pesquisa bloqueada",
        )

        return normalized.startswith(
            failure_prefixes
        )

    @staticmethod
    def _message_indicates_retry(
        message: str,
    ) -> bool:
        normalized = (
            message
            .strip()
            .casefold()
        )

        retryable_terms = (
            "timeout",
            "tempo limite",
            "navegador",
            "página",
            "conexão",
            "não encontrei um elemento",
        )

        return any(
            term in normalized
            for term in retryable_terms
        )

    # ==========================
    # Teclado
    # ==========================

    def _keyboard_write(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.keyboard.write(
            str(parameters["text"])
        )

    def _keyboard_press(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.keyboard.press(
            str(parameters["key"])
        )

    # ==========================
    # Mouse
    # ==========================

    def _mouse_click(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.mouse.click()

    # ==========================
    # Processos
    # ==========================

    def _process_start(
        self,
        parameters: dict[str, Any],
    ) -> str:
        command = parameters["command"]

        if not isinstance(
            command,
            (
                str,
                list,
                tuple,
            ),
        ):
            raise TypeError(
                "O comando deve ser texto, "
                "lista ou tupla."
            )

        return self.process.start(command)

    # ==========================
    # Suporte de TI
    # ==========================

    def _helpdesk_diagnose(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.helpdesk.diagnose(parameters)

    # ==========================
    # Recursos Humanos
    # ==========================

    def _hr_generate_document(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.hr.generate_document(parameters)

    # ==========================
    # Pesquisa mult fonte
    # ==========================

    def _internet_search(
        self,
        parameters: dict[str, Any],
    ) -> str:
        query = str(parameters["query"]).strip()
        max_results = int(parameters.get("max_results", 5))
        freshness = SearchFreshness(
            str(parameters.get("freshness", "any")).strip().lower()
        )
        request = WebSearchRequest(
            query=query,
            max_results=max_results,
            freshness=freshness,
        )
        response = self.internet_search.search(
            request,
            self.internet_principal,
        )
        return response.format_message()

    # ==========================
    # Comercial
    # ==========================

    def _sales_compose_message(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.sales.compose_message(parameters)

    # ==========================
    # Agentes de domínio
    # ==========================

    def _domain_programming_assist(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.domains.programming_assist(parameters)

    def _domain_radiology_support(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.domains.radiology_support(parameters)

    def _domain_wholesale_analysis(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.domains.wholesale_analysis(parameters)

    def _domain_industry_analysis(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.domains.industry_analysis(parameters)

    # ==========================
    # Navegador
    # ==========================

    def _browser_open(
        self,
        parameters: dict[str, Any],
    ) -> str:
        url = str(
            parameters.get(
                "url",
                "https://www.google.com",
            )
        )

        return self.browser.open_url(url)

    def _browser_open_site(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.open_named_site(
            str(parameters["name"])
        )

    def _browser_search(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.search_google(
            str(parameters["query"])
        )

    def _browser_youtube_search(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.search_youtube(
            str(parameters["query"])
        )

    def _browser_click_first_result(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return (
            self.browser
            .click_first_result()
        )

    def _browser_click_second_result(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return (
            self.browser
            .click_second_result()
        )

    def _browser_click_text(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.click_text(
            str(parameters["text"])
        )

    def _browser_fill_input(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.fill_input(
            str(parameters["selector"]),
            str(parameters["text"]),
        )

    def _browser_press_key(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.press_key(
            str(parameters["key"])
        )

    def _browser_wait_page(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.wait_page(
            float(
                parameters.get(
                    "seconds",
                    2,
                )
            )
        )

    def _browser_current_url(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.get_current_url()

    def _browser_page_title(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.get_page_title()

    def _browser_close(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.browser.close()

    # ==========================
    # Arquivos
    # ==========================

    def _file_create_folder(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.files.create_folder(
            str(parameters["path"])
        )

    def _file_create_file(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.files.create_file(
            str(parameters["path"])
        )

    def _file_delete(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.files.delete(
            str(parameters["path"])
        )

    def _file_copy(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.files.copy(
            str(parameters["source"]),
            str(parameters["destination"]),
        )

    def _file_move(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.files.move(
            str(parameters["source"]),
            str(parameters["destination"]),
        )

    def _file_rename(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.files.rename(
            str(parameters["source"]),
            str(parameters["destination"]),
        )

    # ==========================
    # Janelas
    # ==========================

    def _window_minimize(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.minimize()

    def _window_maximize(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.maximize()

    def _window_restore(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.restore()

    def _window_close(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.close()

    def _window_next(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.next()

    def _window_previous(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.previous()

    def _window_desktop(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.show_desktop()

    def _window_focus(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.focus_by_title(
            str(parameters["title"])
        )

    def _window_minimize_title(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.minimize_by_title(
            str(parameters["title"])
        )

    def _window_maximize_title(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.maximize_by_title(
            str(parameters["title"])
        )

    def _window_close_title(
        self,
        parameters: dict[str, Any],
    ) -> str:
        return self.window.close_by_title(
            str(parameters["title"])
        )

    # ==========================
    # Sistema
    # ==========================

    def _system_wait(
        self,
        parameters: dict[str, Any],
    ) -> str:
        seconds = float(
            parameters.get(
                "seconds",
                1,
            )
        )

        if seconds < 0:
            raise ValueError(
                "O tempo de espera não pode "
                "ser negativo."
            )

        time.sleep(seconds)

        return (
            f"Aguardei {seconds:g} segundos."
        )
