from atlas.vision.form_intent import (
    extract_structured_form,
    is_structured_form_attempt,
)


def test_extracts_spoken_multi_field_form() -> None:
    request = extract_structured_form(
        "preencha o campo nome com Ssamir Martins e o campo cidade com Manaus"
    )

    assert request is not None
    assert len(request.fields) == 2
    assert request.fields[0].target == "campo nome"
    assert request.fields[0].text == "Ssamir Martins"
    assert request.fields[1].target == "campo cidade"
    assert request.fields[1].text == "Manaus"


def test_extracts_colon_form_syntax() -> None:
    request = extract_structured_form(
        "preencha o formulário com nome: Ssamir; cidade: Manaus; email: a@b.com"
    )

    assert request is not None
    assert [field.target for field in request.fields] == [
        "campo nome",
        "campo cidade",
        "campo email",
    ]


def test_rejects_sensitive_form_field() -> None:
    command = "preencha o formulário com nome: Ssamir; senha: 123456"

    assert is_structured_form_attempt(command) is True
    assert extract_structured_form(command) is None


def test_single_field_stays_with_stage10_fill() -> None:
    command = "preencha o campo nome com Ssamir"

    assert is_structured_form_attempt(command) is False
    assert extract_structured_form(command) is None


def test_rejects_duplicate_targets() -> None:
    command = "preencha o formulário com nome: A; nome: B"

    assert extract_structured_form(command) is None
