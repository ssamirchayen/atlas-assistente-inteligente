from __future__ import annotations

import time

import pytest
from collections import deque
from threading import Event, Lock

from atlas.voice.continuous import (
    ContinuousEndpointingPolicy,
    ContinuousVoiceListener,
)
from atlas.voice.session import VoiceSession


class _Recognizer:
    pause_threshold = 0.9
    non_speaking_duration = 0.45


class _FakeSpeech:
    def __init__(self, transcripts: list[str]) -> None:
        self.session = VoiceSession()
        self.microphone_enabled = True
        self.recognizer = _Recognizer()
        self._transcripts = deque(transcripts)
        self._lock = Lock()
        self.pause_seen_during_listen: float | None = None
        self.non_speaking_seen_during_listen: float | None = None
        self.phrase_limit_seen_during_listen: float | None = None

    def listen(
        self,
        prompt: str,
        retry_on_failure: bool,
        *,
        timeout: float,
        phrase_time_limit: float,
        verbose: bool,
    ) -> str:
        del prompt, retry_on_failure, timeout, verbose
        self.pause_seen_during_listen = self.recognizer.pause_threshold
        self.non_speaking_seen_during_listen = (
            self.recognizer.non_speaking_duration
        )
        self.phrase_limit_seen_during_listen = phrase_time_limit

        with self._lock:
            transcript = self._transcripts.popleft() if self._transcripts else ""

        self.session.start_listening()
        if not transcript:
            self.session.complete()
            time.sleep(0.005)
            return ""

        self.session.start_processing(transcript)
        return transcript


def test_continuous_listener_allows_natural_pause_and_restores_profile() -> None:
    speech = _FakeSpeech(["Atlas abra o menu Arquivo"])
    received = Event()
    commands: list[str] = []

    def receive(command: str) -> None:
        commands.append(command)
        speech.session.complete()
        received.set()

    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        receive,
        idle_wait=0.01,
    )

    assert listener.start() is True
    assert received.wait(timeout=1) is True
    listener.stop()

    assert commands == ["abra o menu arquivo"]
    assert speech.pause_seen_during_listen == 2.4
    assert speech.non_speaking_seen_during_listen == 0.8
    assert speech.phrase_limit_seen_during_listen == 20.0
    assert speech.recognizer.pause_threshold == 0.9
    assert speech.recognizer.non_speaking_duration == 0.45


def test_continuous_endpointing_policy_validates_limits() -> None:
    with pytest.raises(ValueError, match="pausa contínua"):
        ContinuousEndpointingPolicy(pause_threshold=0)

    with pytest.raises(ValueError, match="não pode superar"):
        ContinuousEndpointingPolicy(
            pause_threshold=1.0,
            non_speaking_duration=1.1,
        )
