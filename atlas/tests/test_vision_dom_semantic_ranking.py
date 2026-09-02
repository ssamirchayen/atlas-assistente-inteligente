from atlas.vision.dom_grounding import (
    _is_search_entry_request,
    _score,
)


def _google_search_input() -> dict[str, str]:
    return {
        "tag": "textarea",
        "role": "combobox",
        "type": "",
        "name": "q",
        "aria_label": "Pesquisar",
        "placeholder": "",
        "title": "",
        "labels": "",
        "text": "",
    }


def _google_images_link() -> dict[str, str]:
    return {
        "tag": "a",
        "role": "",
        "type": "",
        "name": "",
        "aria_label": "Pesquisar imagens",
        "placeholder": "",
        "title": "",
        "labels": "",
        "text": "Imagens",
    }


def _google_voice_button() -> dict[str, str]:
    return {
        "tag": "button",
        "role": "button",
        "type": "button",
        "name": "",
        "aria_label": "Pesquisa por voz",
        "placeholder": "",
        "title": "",
        "labels": "",
        "text": "",
    }


def test_detects_search_entry_phrases() -> None:
    phrases = (
        "campo de pesquisa",
        "barra de pesquisa",
        "caixa de busca",
        "onde eu digito no google",
    )

    for phrase in phrases:
        assert _is_search_entry_request(
            phrase
        )


def test_search_input_beats_images_link() -> None:
    query = "campo de pesquisa"

    input_score = _score(
        query,
        _google_search_input(),
    )
    images_score = _score(
        query,
        _google_images_link(),
    )

    assert input_score >= 0.85
    assert images_score < 0.63
    assert input_score > images_score


def test_search_input_beats_voice_search_button() -> None:
    query = "barra de pesquisa"

    input_score = _score(
        query,
        _google_search_input(),
    )
    voice_score = _score(
        query,
        _google_voice_button(),
    )

    assert input_score >= 0.85
    assert voice_score < 0.63
    assert input_score > voice_score


def test_generic_search_still_matches_input() -> None:
    score = _score(
        "caixa de busca",
        _google_search_input(),
    )

    assert score >= 0.85
