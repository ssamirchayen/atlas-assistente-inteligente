from pathlib import Path


def test_contextual_form_routes_before_stage11_form() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    execute_start = source.index("def execute(self, command: str)")
    contextual_pos = source.index("extract_contextual_form(", execute_start)
    form_pos = source.index("extract_structured_form(", execute_start)

    assert contextual_pos < form_pos


def test_browser_selection_is_structural_and_has_no_coordinate_fallback() -> None:
    source = Path("atlas/automation/browser.py").read_text(encoding="utf-8")
    start = source.index("def select_interactive_option(")
    end = source.index("def click_text(", start)
    region = source[start:end]

    assert "select_option(" in region
    assert 'target.get("tag"' in region
    assert "pyautogui" not in region
    assert "moveTo(" not in region
    assert ".click(" not in region


def test_contextual_flow_keeps_context_and_does_not_submit() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    start = source.index("def _execute_contextual_form(")
    end = source.index("def _execute_structured_option_selection(", start)
    region = source[start:end]

    assert "required_context_token=context_token" in region
    assert "vision_contextual_context_changed" in region
    assert "submit(" not in region
    assert ".click(" not in region
