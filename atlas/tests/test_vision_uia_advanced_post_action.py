from atlas.vision.post_action import verify_uia_post_action


def _state(**target: object) -> dict[str, object]:
    return {"window_title": "Teste", "target": {"exists": True, **target}}


def test_verifies_checkbox_desired_state() -> None:
    result = verify_uia_post_action(
        _state(checked=0),
        _state(checked=1),
        expected_action="check",
    )

    assert result.verified is True
    assert result.reason_code == "uia_target_checked"


def test_verifies_selected_tab_or_list_item() -> None:
    result = verify_uia_post_action(
        _state(selected=False),
        _state(selected=True),
        expected_action="select",
    )

    assert result.verified is True
    assert result.reason_code == "uia_target_selected"


def test_verifies_expand_collapse_state() -> None:
    expanded = verify_uia_post_action(
        _state(expanded=0),
        _state(expanded=1),
        expected_action="expand",
    )
    collapsed = verify_uia_post_action(
        _state(expanded=1),
        _state(expanded=0),
        expected_action="collapse",
    )

    assert expanded.verified is True
    assert expanded.reason_code == "uia_target_expanded"
    assert collapsed.verified is True
    assert collapsed.reason_code == "uia_target_collapsed"


def test_verifies_modern_menu_by_visible_uia_surface_growth() -> None:
    before = {
        "window_title": "Bloco de Notas",
        "menu_surface_count": 3,
        "target": {"exists": True, "expanded": None},
    }
    after = {
        "window_title": "Bloco de Notas",
        "menu_surface_count": 9,
        "target": {"exists": True, "expanded": None},
    }

    result = verify_uia_post_action(
        before,
        after,
        semantic_kind="menu",
        expected_action="expand",
    )

    assert result.verified is True
    assert result.reason_code == "uia_menu_surface_opened"
