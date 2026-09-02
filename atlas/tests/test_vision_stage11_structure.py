from pathlib import Path


def test_form_routes_before_sequence_and_single_fill() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    execute_start = source.index("def execute(self, command: str)")
    form_pos = source.index("extract_structured_form(", execute_start)
    sequence_pos = source.index("extract_structured_sequence(", execute_start)
    fill_pos = source.index("extract_structured_text_input(", execute_start)

    assert form_pos < sequence_pos < fill_pos


def test_form_fill_uses_context_guard_and_no_submit_action() -> None:
    source = Path("atlas/gui/service.py").read_text(encoding="utf-8")
    start = source.index("def _execute_structured_form(")
    end = source.index("def _execute_structured_sequence(", start)
    region = source[start:end]

    assert "required_context_token=context_token" in region
    assert "vision_form_context_changed" in region
    assert ".click(" not in region
    assert "submit(" not in region


def test_browser_exposes_runtime_only_context_token() -> None:
    source = Path("atlas/automation/browser.py").read_text(encoding="utf-8")
    start = source.index("def get_structural_context_token(")
    end = source.index("def _synchronize_current_page(", start)
    region = source[start:end]

    assert "id(page)" in region
    assert "page.url" not in region
