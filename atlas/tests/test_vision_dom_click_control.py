from pathlib import Path


def test_browser_click_requires_focused_page() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def click_interactive_element("
    )
    end = source.index(
        "# INTERAÇÃO",
        start,
    )
    method = source[start:end]

    assert "document.hasFocus()" in method
    assert "locator.click(" in method
    assert "pyautogui" not in method


def test_gui_click_is_before_router_and_planner() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    click_pos = source.index(
        "click_target = extract_click_target("
    )
    router_pos = source.index(
        "route_priority(execution_command)"
    )
    controller_pos = source.index(
        "self.controller.execute(execution_command)"
    )

    assert click_pos < router_pos
    assert click_pos < controller_pos


def test_vision_coordinate_click_is_not_enabled() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    click_start = source.index(
        "click_target = extract_click_target("
    )
    click_end = source.index(
        "priority_result =",
        click_start,
    )
    flow = source[
        click_start:click_end
    ]

    assert "click_interactive_element(" in flow
    assert "pyautogui.click" not in flow
    assert "locate_on_screen(" not in flow


def test_controlled_click_threshold_is_85_percent() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    assert "match.confidence < 0.85" in source
