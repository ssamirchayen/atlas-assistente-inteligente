from atlas.vision.uia_action_intent import extract_windows_uia_action


def test_rejects_generic_menu_without_specific_name() -> None:
    assert extract_windows_uia_action("abra o menu") is None
    assert extract_windows_uia_action("feche o menu") is None


def test_keeps_specific_menu_action() -> None:
    request = extract_windows_uia_action("abra o menu Arquivo")

    assert request is not None
    assert request.action == "expand"
    assert request.target == "menu Arquivo"
