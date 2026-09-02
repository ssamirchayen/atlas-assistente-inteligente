from pathlib import Path


def test_browser_dom_grounding_is_read_only() -> None:
    source = Path(
        "atlas/automation/browser.py"
    ).read_text(encoding="utf-8")

    start = source.index(
        "def inspect_visible_interactive_elements"
    )
    end = source.index(
        "# INTERAÇÃO",
        start,
    )
    method = source[start:end]

    assert ".click(" not in method
    assert ".fill(" not in method


def test_gui_prefers_dom_before_vision_model() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    dom_pos = source.index(
        "locate_browser_dom_element("
    )
    vision_pos = source.index(
        "self.kernel.vision.locate_on_screen("
    )

    assert dom_pos < vision_pos
