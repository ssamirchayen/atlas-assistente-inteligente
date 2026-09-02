from pathlib import Path


def test_gui_result_supports_overlay() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    assert "overlay: VisionOverlaySpec | None = None" in source
    assert "VisionOverlaySpec.from_grounding(" in source


def test_window_renders_overlay_on_gui_thread() -> None:
    source = Path(
        "atlas/gui/window.py"
    ).read_text(encoding="utf-8")

    assert "VisionOverlayWindow" in source
    assert "self.vision_overlay.show_spec(result.overlay)" in source


def test_overlay_is_click_through() -> None:
    source = Path(
        "atlas/gui/vision_overlay.py"
    ).read_text(encoding="utf-8")

    assert "WA_TransparentForMouseEvents" in source
    assert "WA_ShowWithoutActivating" in source
