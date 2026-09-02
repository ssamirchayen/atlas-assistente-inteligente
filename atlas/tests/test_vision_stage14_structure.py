from pathlib import Path

from atlas.gui.service import GuiCommandResult


def test_gui_result_exposes_explicit_confirmation_state() -> None:
    result = GuiCommandResult(
        message="aguardando",
        source="vision_final_action",
        requires_confirmation=True,
        confirmation_token="TOKEN123",
    )

    assert result.requires_confirmation is True
    assert result.confirmation_token == "TOKEN123"


def test_final_activation_is_revalidated_and_has_no_coordinate_fallback() -> None:
    source = Path("atlas/automation/browser.py").read_text(encoding="utf-8")
    start = source.index("def activate_final_control(")
    end = source.index("def fill_input(", start)
    region = source[start:end]

    assert "inspect_interaction_state(" in region
    assert "trial=True" in region
    assert "final_terms" in region
    assert "pyautogui" not in region
    assert "moveTo(" not in region


def test_confirmation_route_precedes_all_regular_vision_actions() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    execute_start = source.index("def execute(self, command: str)")
    confirm_pos = source.index(
        "extract_final_action_confirmation(", execute_start
    )
    click_pos = source.index("extract_click_target(", execute_start)

    assert confirm_pos < click_pos

