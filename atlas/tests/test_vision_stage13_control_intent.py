import pytest

from atlas.vision.control_intent import extract_structured_control


@pytest.mark.parametrize(
    ("command", "action", "target"),
    [
        ("marque a caixa de seleção novidades", "check", "novidades"),
        ("desmarque o checkbox novidades", "uncheck", "novidades"),
        ("ative o switch modo escuro", "check", "modo escuro"),
        ("desative o interruptor som", "uncheck", "som"),
        ("selecione a opção email", "select", "email"),
    ],
)
def test_extracts_explicit_structural_controls(
    command: str,
    action: str,
    target: str,
) -> None:
    request = extract_structured_control(command)

    assert request is not None
    assert request.action == action
    assert target in request.target.casefold()


def test_rejects_unchecking_radio_and_generic_targets() -> None:
    assert extract_structured_control("desmarque a opção email") is None
    assert extract_structured_control("marque novidades") is None


@pytest.mark.parametrize(
    "command",
    [
        "marque a caixa confirmar compra",
        "ative o switch pagar agora",
        "marque a opção excluir cadastro",
    ],
)
def test_blocks_final_or_sensitive_actions(command: str) -> None:
    assert extract_structured_control(command) is None

