from atlas.vision.text_input_intent import extract_structured_text_input


def test_extracts_type_in_search_bar_and_preserves_text() -> None:
    request = extract_structured_text_input(
        'digite "Atlas Vision 10." na barra de pesquisa.'
    )

    assert request is not None
    assert request.target == "barra de pesquisa"
    assert request.text == "Atlas Vision 10."


def test_extracts_fill_field_with_text() -> None:
    request = extract_structured_text_input(
        "preencha o campo Nome com Ssamir Martins"
    )

    assert request is not None
    assert request.target == "campo Nome"
    assert request.text == "Ssamir Martins"


def test_rejects_generic_typing_without_structural_target() -> None:
    assert extract_structured_text_input("digite olá") is None
