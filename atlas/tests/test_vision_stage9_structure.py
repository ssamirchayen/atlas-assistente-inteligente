from pathlib import Path


def test_stage9_action_router_runs_before_legacy_click_path() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")

    advanced = source.index("extract_windows_uia_action(execution_command)")
    legacy = source.index("click_target = extract_click_target(")

    assert advanced < legacy


def test_stage9_never_adds_visual_coordinate_action_fallback() -> None:
    source = Path("atlas/vision/uia_grounding.py").read_text(encoding="utf-8")
    start = source.index("def perform_windows_uia_action(")
    action_section = source[start:]

    assert "pyautogui.click" not in action_section
    assert "click_input" not in action_section
    assert "mouse." not in action_section
