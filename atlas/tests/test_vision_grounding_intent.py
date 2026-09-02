from atlas.vision.grounding_intent import extract_grounding_query


def test_extracts_where_is_query() -> None:
    assert extract_grounding_query(
        "onde está o botão enviar?"
    ) == "botao enviar"


def test_extracts_localize_query() -> None:
    assert extract_grounding_query(
        "localize o campo de mensagem"
    ) == "campo de mensagem"


def test_does_not_absorb_click_command() -> None:
    assert extract_grounding_query(
        "clique no botão enviar"
    ) is None
