from atlas.vision.post_action import verify_uia_post_action


def _state(
    *,
    title: str = "Bloco de Notas",
    focused: bool = False,
    checked: bool | None = None,
    selected: bool | None = None,
) -> dict[str, object]:
    return {
        "window_title": title,
        "target": {
            "exists": True,
            "focused": focused,
            "checked": checked,
            "selected": selected,
            "enabled": True,
        },
    }


def test_uia_text_field_is_verified_by_focus() -> None:
    result = verify_uia_post_action(
        _state(focused=False),
        _state(focused=True),
        semantic_kind="text_input",
    )

    assert result.verified is True
    assert result.reason_code == "uia_target_focused"


def test_uia_toggle_change_is_verified() -> None:
    result = verify_uia_post_action(
        _state(checked=False),
        _state(checked=True),
    )

    assert result.verified is True
    assert result.reason_code == "uia_target_state_changed"


def test_uia_window_change_is_verified() -> None:
    result = verify_uia_post_action(
        _state(title="Janela A"),
        _state(title="Janela B"),
    )

    assert result.verified is True
    assert result.reason_code == "uia_window_changed"


def test_uia_unchanged_button_is_inconclusive() -> None:
    result = verify_uia_post_action(_state(), _state())

    assert result.verified is False
    assert result.reason_code == "uia_post_action_inconclusive"
