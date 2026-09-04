from __future__ import annotations

from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_mature_voice_api_was_restored() -> None:
    root = _root()
    continuous = (root / "atlas/voice/continuous.py").read_text(encoding="utf-8")
    interruption = (root / "atlas/voice/interruption.py").read_text(encoding="utf-8")
    session = (root / "atlas/voice/session.py").read_text(encoding="utf-8")

    assert "class ContinuousVoiceListener" in continuous
    assert "class VoiceInterruptionMonitor" in interruption
    assert "class VoiceSnapshot" in session
    assert "class VoiceState" in session


def test_frozen_tts_uses_direct_python_api() -> None:
    root = _root()
    tts = (root / "atlas/voice/tts.py").read_text(encoding="utf-8")
    speech = (root / "atlas/voice/speech.py").read_text(encoding="utf-8")

    assert "def synthesize(" in tts
    assert "edge_tts.Communicate(" in tts
    assert "self.neural_voice.synthesize(" in speech
    assert "self._neural_player.play(" in speech
    assert "self._neural_player.stop()" in speech


def test_pyinstaller_collects_edge_tts() -> None:
    spec = (_root() / "packaging/atlas.spec").read_text(encoding="utf-8")

    assert 'collect_all("edge_tts")' in spec
    assert '"atlas.voice.continuous"' in spec
    assert '"atlas.voice.interruption"' in spec


def test_voice_selftest_is_exposed_by_gui_entrypoint() -> None:
    gui_main = (_root() / "gui_main.py").read_text(encoding="utf-8")

    assert '"--voice-selftest"' in gui_main
    assert "SpeechInterface.runtime_self_test()" in gui_main
