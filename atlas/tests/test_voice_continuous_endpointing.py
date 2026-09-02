from __future__ import annotations

from atlas.voice.continuous import (
    ContinuousEndpointingPolicy,
    ContinuousVoiceListener,
)
from atlas.voice.session import VoiceSession


class _Recognizer:
    pause_threshold = 0.9
    non_speaking_duration = 0.45


class _Speech:
    def __init__(self) -> None:
        self.session = VoiceSession()
        self.microphone_enabled = True
        self.recognizer = _Recognizer()


def test_effective_phrase_limit_never_uses_fast_profile_cutoff() -> None:
    listener = ContinuousVoiceListener(
        _Speech(),  # type: ignore[arg-type]
        lambda command: None,
        phrase_time_limit=10.0,
    )

    assert listener._effective_phrase_time_limit() == 20.0


def test_custom_endpointing_can_be_tuned_without_global_profile() -> None:
    speech = _Speech()
    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        lambda command: None,
        endpointing_policy=ContinuousEndpointingPolicy(
            pause_threshold=2.8,
            non_speaking_duration=1.0,
            minimum_phrase_time_limit=24.0,
        ),
    )

    snapshot = listener._apply_continuous_endpointing()

    assert speech.recognizer.pause_threshold == 2.8
    assert speech.recognizer.non_speaking_duration == 1.0
    assert listener._effective_phrase_time_limit() == 24.0

    listener._restore_continuous_endpointing(snapshot)

    assert speech.recognizer.pause_threshold == 0.9
    assert speech.recognizer.non_speaking_duration == 0.45
