import pytest

from atlas.vision.intent import is_read_only_vision_command


@pytest.mark.parametrize(
    "command",
    [
        "Atlas, o que você está vendo?",
        "o que tem nessa tela?",
        "tem algum erro nessa tela?",
        "qual programa está aberto?",
        "o que está escrito aqui?",
        "descreva minha tela",
        "analise esta tela",
    ],
)
def test_read_only_vision_commands_are_detected(command: str) -> None:
    assert is_read_only_vision_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "clique no botão que está na tela",
        "abra o programa que você está vendo",
        "digite nesse campo",
        "qual é a capital do Brasil?",
        "me explique como funciona uma API",
    ],
)
def test_actions_and_normal_chat_are_not_vision(command: str) -> None:
    assert not is_read_only_vision_command(command)
