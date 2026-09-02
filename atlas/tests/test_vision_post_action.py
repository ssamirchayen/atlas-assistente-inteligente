from atlas.vision.post_action import verify_click_post_action


def _state(
    *,
    url: str = "https://example.test/",
    title: str = "Example",
    focused: bool = False,
    checked: bool | None = None,
    aria_expanded: str = "",
    dialogs: int = 0,
    expanded: int = 0,
    interactive_count: int = 10,
) -> dict[str, object]:
    return {
        "url": url,
        "title": title,
        "dialog_count": dialogs,
        "expanded_count": expanded,
        "interactive_count": interactive_count,
        "target": {
            "exists": True,
            "focused": focused,
            "checked": checked,
            "aria_pressed": "",
            "aria_expanded": aria_expanded,
            "aria_selected": "",
        },
    }


def test_search_input_is_verified_by_post_focus() -> None:
    before = _state(focused=True)
    after = _state(focused=True)

    result = verify_click_post_action(
        before,
        after,
        semantic_kind="search_input",
    )

    assert result.verified is True
    assert result.reason_code == "target_focused"


def test_navigation_change_verifies_click_effect() -> None:
    before = _state(url="https://example.test/")
    after = _state(url="https://example.test/next")

    result = verify_click_post_action(before, after)

    assert result.verified is True
    assert result.reason_code == "navigation_changed"


def test_toggle_state_change_verifies_click_effect() -> None:
    before = _state(checked=False)
    after = _state(checked=True)

    result = verify_click_post_action(before, after)

    assert result.verified is True
    assert result.reason_code == "target_state_changed"


def test_expanded_state_change_verifies_click_effect() -> None:
    before = _state(aria_expanded="false", expanded=0)
    after = _state(aria_expanded="true", expanded=1)

    result = verify_click_post_action(before, after)

    assert result.verified is True
    assert result.reason_code == "target_state_changed"


def test_unchanged_generic_button_is_inconclusive() -> None:
    before = _state(focused=False)
    after = _state(focused=False)

    result = verify_click_post_action(before, after)

    assert result.verified is False
    assert result.reason_code == "post_action_inconclusive"
