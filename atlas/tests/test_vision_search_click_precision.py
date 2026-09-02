from pathlib import Path

from atlas.vision.dom_grounding import (
    _search_input_bonus,
    _semantic_kind,
)


def test_search_phrases_are_same_intent() -> None:
    phrases = (
        "campo de pesquisa",
        "barra de pesquisa",
        "caixa de busca",
        "onde eu digito no google",
    )

    assert {
        _semantic_kind(phrase)
        for phrase in phrases
    } == {"search_input"}


def test_google_main_search_field_gets_strong_bonus() -> None:
    candidate = {
        "tag": "textarea",
        "role": "combobox",
        "type": "",
        "name": "q",
        "aria_label": "Pesquisar",
        "placeholder": "",
    }

    assert _search_input_bonus(
        candidate
    ) >= 1.0


def test_click_has_search_semantic_resolver() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def click_interactive_element("
    )
    end = source.index(
        "# INTERAÇÃO",
        start,
    )
    method = source[start:end]

    assert 'semanticKind === "search_input"' in method
    assert 'data.name === "q"' in method
    assert 'data.role === "searchbox"' in method


def test_service_passes_semantic_kind() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    assert "match.semantic_kind" in source
    assert "retry_match.semantic_kind" in source
