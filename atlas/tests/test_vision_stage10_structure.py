from pathlib import Path


def test_browser_fill_is_structural_and_has_no_coordinate_fallback() -> None:
    source = Path("atlas/automation/browser.py").read_text(encoding="utf-8")
    start = source.index("def fill_interactive_element(")
    end = source.index("def click_text(", start)
    region = source[start:end]

    assert "locator.fill(" in region
    assert "password" in region
    assert "pyautogui" not in region
    assert "click(" not in region


def test_service_routes_sequence_and_fill_before_generic_uia_action() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    execute_start = source.index("def execute(self, command: str)")
    sequence_pos = source.index("extract_structured_sequence(", execute_start)
    fill_pos = source.index("extract_structured_text_input(", execute_start)
    uia_pos = source.index("extract_windows_uia_action(", execute_start)

    assert sequence_pos < fill_pos < uia_pos
