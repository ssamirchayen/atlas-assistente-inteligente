from atlas.vision.dom_grounding import _score


def test_google_searchbox_scores_high() -> None:
    candidate = {
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

    assert _score(
        "campo de pesquisa",
        candidate,
    ) >= 0.8


def test_irrelevant_button_scores_lower() -> None:
    candidate = {
        "tag": "button",
        "role": "button",
        "type": "button",
        "name": "",
        "aria_label": "Google Apps",
        "placeholder": "",
        "title": "",
        "labels": "",
        "text": "",
    }

    assert _score(
        "campo de pesquisa",
        candidate,
    ) < 0.63
