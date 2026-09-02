from atlas.vision.option_select_intent import (
    extract_contextual_form,
    extract_structured_option_selection,
    is_contextual_form_attempt,
)


def test_extracts_direct_option_selection() -> None:
    request = extract_structured_option_selection(
        "selecione Amazonas no campo estado"
    )

    assert request is not None
    assert request.option == "Amazonas"
    assert request.target == "campo estado"


def test_extracts_contextual_fill_and_selection() -> None:
    request = extract_contextual_form(
        "preencha o campo nome com Ssamir e o campo cidade com Manaus "
        "e selecione Amazonas no campo estado"
    )

    assert request is not None
    assert [field.target for field in request.fields] == [
        "campo nome",
        "campo cidade",
    ]
    assert [item.option for item in request.selections] == ["Amazonas"]
    assert request.selections[0].target == "campo estado"


def test_contextual_attempt_rejects_sensitive_target() -> None:
    command = "preencha o campo nome com Ssamir e selecione 123 na lista senha"

    assert is_contextual_form_attempt(command) is True
    assert extract_contextual_form(command) is None


def test_rejects_duplicate_target_across_fill_and_selection() -> None:
    command = "preencha o campo estado com AM e selecione Amazonas no campo estado"

    assert extract_contextual_form(command) is None
