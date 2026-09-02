from pathlib import Path


def test_read_only_grounding_order_is_qt_dom_uia_vision() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")

    start = source.index("grounding_query = extract_grounding_query(")
    end = source.index("# Vision read-only", start)
    flow = source[start:end]

    assert flow.index("locate_qt_widget(") < flow.index(
        "locate_browser_dom_element("
    )
    assert flow.index("locate_browser_dom_element(") < flow.index(
        "locate_windows_uia_element("
    )
    assert flow.index("locate_windows_uia_element(") < flow.index(
        "locate_on_screen("
    )


def test_controlled_action_order_is_dom_then_uia_without_visual_click() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")

    start = source.index("click_target = extract_click_target(")
    end = source.index("priority_result =", start)
    flow = source[start:end]

    assert flow.index("find_browser_dom_match(") < flow.index(
        "find_windows_uia_match("
    )
    assert "activate_windows_uia_match(" in flow
    assert "pyautogui.click" not in flow
    assert "locate_on_screen(" not in flow


def test_uia_module_has_no_coordinate_click_fallback() -> None:
    source = Path("atlas/vision/uia_grounding.py").read_text(encoding="utf-8")

    assert "click_input(" not in source
    assert "import pyautogui" not in source
    assert "pyautogui." not in source
    assert "iface_invoke" in source
    assert "iface_toggle" in source
    assert "iface_selection_item" in source
    assert "set_focus" in source


def test_uia_revalidates_fingerprint_before_action() -> None:
    source = Path("atlas/vision/uia_grounding.py").read_text(encoding="utf-8")

    assert "_resolve_active_wrapper(match)" in source
    assert "_fingerprint_score" in source
    assert "match.process_id" in source
    assert "process_id == os.getpid()" in source


def test_validation_lab_registers_stage_8_windows_scenarios() -> None:
    source = Path("validation/scenarios/vision.json").read_text(encoding="utf-8")

    assert '"id": "VISION-005"' in source
    assert '"id": "VISION-006"' in source
    assert source.count('"phase": "vision-stage-8"') >= 2
