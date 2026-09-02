from pathlib import Path


def test_qt_grounding_module_exists() -> None:
    source = Path(
        "atlas/vision/qt_grounding.py"
    ).read_text(encoding="utf-8")

    assert "def locate_qt_widget(" in source
    assert "mapToGlobal" in source
    assert "VisionBoundingBox" in source


def test_gui_tries_qt_grounding_before_model() -> None:
    source = Path(
        "atlas/gui/service.py"
    ).read_text(encoding="utf-8")

    assert source.index(
        "locate_qt_widget("
    ) < source.index(
        "self.kernel.vision.locate_on_screen("
    )
