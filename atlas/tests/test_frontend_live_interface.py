from __future__ import annotations

from pathlib import Path

from atlas.gui.theme import VERSION_LABEL, application_stylesheet


def test_live_interface_version_label() -> None:
    assert "SPRINT 26" in VERSION_LABEL
    assert "LIVE INTERFACE" in VERSION_LABEL


def test_orb_source_has_core_states() -> None:
    source = Path("atlas/gui/orb.py").read_text(encoding="utf-8")
    for state in ("ONLINE", "OUVINDO", "PROCESSANDO", "FALANDO", "ERRO"):
        assert f'"{state}"' in source


def test_orb_source_has_animation_timer() -> None:
    source = Path("atlas/gui/orb.py").read_text(encoding="utf-8")
    assert "self._timer.start(33)" in source
    assert "def _advance" in source
    assert "QConicalGradient" in source


def test_stylesheet_contains_live_components() -> None:
    stylesheet = application_stylesheet()
    assert "QLabel#orbState" in stylesheet
    assert "QLabel#capabilityChip" in stylesheet
    assert "QProgressBar#processingBar" in stylesheet


def test_window_updates_orb_from_operational_status() -> None:
    source = Path("atlas/gui/window.py").read_text(encoding="utf-8")
    assert "self.atlas_orb.set_state(normalized)" in source
    assert "self.processing_bar.setRange(0, 0)" in source
    assert "self.clock_label.setText" in source
