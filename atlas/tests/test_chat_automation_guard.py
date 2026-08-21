from atlas.intent.analyzer import IntentAnalyzer


def test_api_explanation_is_chat() -> None:
    intent = IntentAnalyzer().analyze(
        "me explique como funciona uma API e de alguns exemplos"
    )

    assert intent.name == "chat"
    assert intent.confidence >= 0.99


def test_explaining_chrome_does_not_mean_open_program() -> None:
    intent = IntentAnalyzer().analyze(
        "me explique como abrir o Chrome"
    )

    assert intent.name == "chat"


def test_explaining_files_does_not_mean_open_file() -> None:
    intent = IntentAnalyzer().analyze(
        "o que e um arquivo Python"
    )

    assert intent.name == "chat"


def test_direct_chrome_command_remains_automation() -> None:
    intent = IntentAnalyzer().analyze("abra o Chrome")

    assert intent.name == "open_program"


def test_direct_project_command_remains_automation() -> None:
    intent = IntentAnalyzer().analyze("rodar projeto")

    assert intent.name == "run_project"
