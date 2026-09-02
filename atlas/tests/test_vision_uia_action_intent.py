from atlas.vision.uia_action_intent import extract_windows_uia_action


def test_extracts_checkbox_actions() -> None:
    check = extract_windows_uia_action("marque a caixa de seleção modo escuro")
    uncheck = extract_windows_uia_action(
        "desmarque a caixa de seleção modo escuro"
    )

    assert check is not None
    assert check.action == "check"
    assert "modo escuro" in check.target
    assert uncheck is not None
    assert uncheck.action == "uncheck"


def test_extracts_selection_and_focus_actions() -> None:
    select = extract_windows_uia_action("selecione a aba Exibir")
    focus = extract_windows_uia_action("foque no campo Nome")

    assert select is not None
    assert select.action == "select"
    assert select.target == "aba Exibir"
    assert focus is not None
    assert focus.action == "focus"
    assert focus.target == "campo Nome"


def test_open_is_restricted_to_expandable_controls() -> None:
    menu = extract_windows_uia_action("abra o menu Arquivo")
    google = extract_windows_uia_action("abra o Google")

    assert menu is not None
    assert menu.action == "expand"
    assert google is None


def test_rejects_multiple_actions_in_one_command() -> None:
    assert (
        extract_windows_uia_action(
            "selecione a aba Exibir e depois marque a caixa"
        )
        is None
    )


def test_accepts_spoken_abre_menu_variant() -> None:
    request = extract_windows_uia_action("abre o menu arquivo")

    assert request is not None
    assert request.action == "expand"
    assert request.target == "menu arquivo"
