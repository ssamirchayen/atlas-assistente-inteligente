from pathlib import Path


def test_control_state_uses_playwright_state_without_coordinates() -> None:
    source = Path("atlas/automation/browser.py").read_text(encoding="utf-8")
    start = source.index("def set_interactive_control_state(")
    end = source.index("# INTERAÇÃO", start)
    region = source[start:end]

    assert "set_checked(" in region
    assert "inspect_interaction_state(" in region
    assert ".click(" not in region
    assert "pyautogui" not in region
    assert "moveTo(" not in region


def test_control_route_precedes_generic_uia_route() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    execute_start = source.index("def execute(self, command: str)")
    control_pos = source.index("extract_structured_control(", execute_start)
    uia_pos = source.index("extract_windows_uia_action(", execute_start)

    assert control_pos < uia_pos


def test_failed_reversible_control_has_bounded_rollback() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    start = source.index("def _execute_structured_control(")
    end = source.index("def _prepare_final_action(", start)
    region = source[start:end]

    assert "decide_recovery(" in region
    assert "rollback_allowed" in region
    assert "Não repeti" in region

