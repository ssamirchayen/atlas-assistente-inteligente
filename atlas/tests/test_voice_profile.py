from __future__ import annotations

import pytest

from atlas.voice.profile import (
    ACCURATE_VOICE_PROFILE,
    BALANCED_VOICE_PROFILE,
    FAST_VOICE_PROFILE,
    VoicePerformanceProfile,
    resolve_voice_profile,
)
from atlas.voice.speech import SpeechInterface


def test_balanced_profile_preserves_existing_voice_behavior() -> None:
    profile = resolve_voice_profile("balanced")

    assert profile is BALANCED_VOICE_PROFILE
    assert profile.pause_threshold == 1.7
    assert profile.calibration_duration == 1.0
    assert profile.command_timeout == 10.0


def test_fast_profile_reduces_waiting_windows() -> None:
    assert FAST_VOICE_PROFILE.pause_threshold < (
        BALANCED_VOICE_PROFILE.pause_threshold
    )
    assert FAST_VOICE_PROFILE.calibration_duration < (
        BALANCED_VOICE_PROFILE.calibration_duration
    )
    assert FAST_VOICE_PROFILE.command_timeout < (
        BALANCED_VOICE_PROFILE.command_timeout
    )
    assert FAST_VOICE_PROFILE.continuous_idle_wait < (
        BALANCED_VOICE_PROFILE.continuous_idle_wait
    )


def test_accurate_profile_allows_longer_natural_pauses() -> None:
    assert ACCURATE_VOICE_PROFILE.pause_threshold > (
        BALANCED_VOICE_PROFILE.pause_threshold
    )
    assert ACCURATE_VOICE_PROFILE.command_phrase_time_limit > (
        BALANCED_VOICE_PROFILE.command_phrase_time_limit
    )


def test_unknown_profile_falls_back_to_balanced() -> None:
    assert resolve_voice_profile("desconhecido") is BALANCED_VOICE_PROFILE


def test_custom_profile_is_preserved() -> None:
    profile = VoicePerformanceProfile(
        name="custom",
        pause_threshold=1.0,
        non_speaking_duration=0.5,
        phrase_threshold=0.1,
        calibration_duration=0.5,
        command_timeout=5.0,
        command_phrase_time_limit=10.0,
        continuous_listen_timeout=1.0,
        continuous_phrase_time_limit=8.0,
        continuous_idle_wait=0.05,
    )

    assert resolve_voice_profile(profile) is profile


def test_profile_rejects_invalid_timing() -> None:
    with pytest.raises(ValueError, match="positivos"):
        VoicePerformanceProfile(
            name="invalid",
            pause_threshold=0,
            non_speaking_duration=0.5,
            phrase_threshold=0.1,
            calibration_duration=0.5,
            command_timeout=5.0,
            command_phrase_time_limit=10.0,
            continuous_listen_timeout=1.0,
            continuous_phrase_time_limit=8.0,
            continuous_idle_wait=0.05,
        )


def test_speech_interface_applies_fast_profile() -> None:
    speech = SpeechInterface(
        microphone_enabled=False,
        performance_profile="fast",
    )

    assert speech.performance_profile is FAST_VOICE_PROFILE
    assert speech.recognizer.pause_threshold == 0.9
    assert speech.recognizer.non_speaking_duration == 0.45
    assert speech.recognizer.phrase_threshold == 0.15
    assert speech.performance_snapshot() == {
        "profile": "fast",
        "cycles": 0,
        "completed": 0,
        "interrupted": 0,
        "errors": 0,
        "average_total_ms": None,
        "maximum_total_ms": None,
    }
