from pathlib import Path


def test_explicit_uia_action_never_falls_through_to_program_router() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")

    intent_pos = source.index("uia_action = extract_windows_uia_action")
    explicit_pos = source.index("if uia_action is not None:", intent_pos)
    router_pos = source.index("self.kernel.router.route", explicit_pos)

    block = source[explicit_pos:router_pos]
    assert "uia_runtime_unavailable" in block
    assert "return GuiCommandResult" in block


def test_uia_action_retries_structural_grounding_briefly() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")

    method_pos = source.index("def _execute_windows_uia_action")
    next_method = source.index("def _inspect_click_state", method_pos)
    block = source[method_pos:next_method]

    assert "for delay_seconds in (0.0, 0.15, 0.30, 0.50):" in block
    assert "find_windows_uia_match" in block
