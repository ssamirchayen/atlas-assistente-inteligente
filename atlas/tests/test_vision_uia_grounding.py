from atlas.vision.uia_grounding import (
    WindowsUIAMatch,
    _score_uia_candidate,
)


def test_uia_button_exact_name_scores_high() -> None:
    candidate = {
        "name": "Salvar",
        "automation_id": "SaveButton",
        "control_type": "Button",
        "class_name": "Button",
        "enabled": True,
    }

    assert _score_uia_candidate("botão salvar", candidate) >= 0.85


def test_uia_search_field_scores_high() -> None:
    candidate = {
        "name": "Pesquisar",
        "automation_id": "SearchBox",
        "control_type": "Edit",
        "class_name": "TextBox",
        "enabled": True,
    }

    assert _score_uia_candidate("campo de pesquisa", candidate) >= 0.85


def test_uia_disabled_element_is_penalized() -> None:
    enabled = {
        "name": "Salvar",
        "control_type": "Button",
        "enabled": True,
    }
    disabled = dict(enabled, enabled=False)

    assert _score_uia_candidate("salvar", disabled) < _score_uia_candidate(
        "salvar", enabled
    )


def test_uia_match_keeps_structural_fingerprint() -> None:
    fields = WindowsUIAMatch.__dataclass_fields__

    assert "fingerprint" in fields
    assert "window_title" in fields
    assert "process_id" in fields
    assert hasattr(WindowsUIAMatch, "action_fingerprint")
