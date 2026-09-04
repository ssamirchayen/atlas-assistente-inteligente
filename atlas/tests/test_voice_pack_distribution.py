from __future__ import annotations

from pathlib import Path

from atlas.voice.continuous import ContinuousVoiceListener
from atlas.voice.interruption import VoiceInterruptionMonitor
from atlas.voice.playback import WindowsMciPlayer
from atlas.voice.profile import resolve_voice_profile
from atlas.voice.session import VoiceSession
from atlas.voice.tts import EdgeTTSProvider


def test_fast_profile_matches_mature_voice_pack() -> None:
    profile = resolve_voice_profile("fast")

    assert profile.pause_threshold == 0.9
    assert profile.calibration_duration == 0.5
    assert profile.command_timeout == 6.0


def test_default_edge_voice_is_antonio() -> None:
    assert EdgeTTSProvider().voice == "pt-BR-AntonioNeural"


def test_mature_voice_components_are_available() -> None:
    assert callable(ContinuousVoiceListener)
    assert callable(VoiceInterruptionMonitor)
    assert callable(VoiceSession)
    assert callable(WindowsMciPlayer)


def test_spec_embeds_edge_tts() -> None:
    root = Path(__file__).resolve().parents[2]
    spec = (root / "packaging/atlas.spec").read_text(encoding="utf-8")

    assert 'collect_all("edge_tts")' in spec
    assert '"atlas.voice.continuous"' in spec
    assert '"atlas.voice.interruption"' in spec
