from atlas.vision.action_intent import (
    extract_click_target,
)


def test_extract_click_target() -> None:
    assert extract_click_target(
        "clique no campo de pesquisa"
    ) == "campo de pesquisa"

    assert extract_click_target(
        "Clica na barra de pesquisa!"
    ) == "barra de pesquisa"


def test_requires_explicit_click_verb() -> None:
    assert extract_click_target(
        "onde está o campo de pesquisa?"
    ) is None


def test_rejects_multiple_click_sequence() -> None:
    assert extract_click_target(
        "clique em pesquisar e depois clique em imagens"
    ) is None

    assert extract_click_target(
        "duplo clique no arquivo"
    ) is None
