from __future__ import annotations

from unittest.mock import MagicMock

from atlas.agents.browser import BrowserAgent
from atlas.automation.browser import BrowserAutomation
from atlas.browser.session import BrowserSession


def make_page(url: str = "https://www.google.com") -> MagicMock:
    page = MagicMock()
    page.url = url
    page.is_closed.return_value = False
    page.title.return_value = "Página de teste"
    return page


def test_browser_agent_understands_previous_search_with_click_variant() -> None:
    actions = BrowserAgent().plan(
        "click no primeiro resultado da pesquisa anterior"
    )

    assert len(actions) == 1
    assert actions[0].type == "browser.click_first_result"


def test_last_search_is_restored_after_manual_navigation() -> None:
    session = BrowserSession()
    automation = BrowserAutomation(session)
    page = make_page("https://example.com/noticia")
    search_url = "https://www.google.com/search?q=carros+usados"
    context = MagicMock()
    context.pages = [page]
    automation._context = context
    automation._last_search_page = page
    automation._last_search_url = search_url

    restored_page = automation._get_last_search_page()

    assert restored_page is page
    page.bring_to_front.assert_called_once_with()
    page.goto.assert_called_once_with(
        search_url,
        wait_until="domcontentloaded",
        timeout=30_000,
    )
    assert session.get_last_search_tab() is not None


def test_google_search_is_recorded_in_shared_browser_session() -> None:
    session = BrowserSession()
    automation = BrowserAutomation(session)
    page = make_page()
    automation._run_with_recovery = MagicMock(
        side_effect=lambda operation: operation(page)
    )

    result = automation.search_google("carros usados")

    assert result == "Pesquisei no Google por: carros usados"
    search_tab = session.get_last_search_tab()
    assert search_tab is not None
    assert search_tab.search_query == "carros usados"
    assert search_tab.tab_type == "google_search"


def test_click_waits_for_result_and_keeps_search_reference() -> None:
    automation = BrowserAutomation()
    page = make_page(
        "https://www.google.com/search?q=carros+usados"
    )
    result_links = MagicMock()
    selected_result = MagicMock()
    heading = MagicMock()
    heading.inner_text.return_value = "Carros usados em Manaus"
    selected_result.locator.return_value = heading
    result_links.nth.return_value = selected_result
    page.locator.return_value = result_links
    automation._get_last_search_page = MagicMock(return_value=page)
    automation._get_open_pages = MagicMock(return_value=[page])
    automation._run_with_recovery = MagicMock(
        side_effect=lambda operation: operation(page)
    )

    result = automation.click_first_result()

    assert result == (
        "Cliquei no primeiro resultado: Carros usados em Manaus"
    )
    page.locator.assert_called_once_with(
        "#search a:has(h3), a:has(h3)"
    )
    result_links.nth.assert_called_once_with(0)
    selected_result.wait_for.assert_called_once_with(
        state="visible",
        timeout=15_000,
    )
    selected_result.click.assert_called_once_with(timeout=15_000)
