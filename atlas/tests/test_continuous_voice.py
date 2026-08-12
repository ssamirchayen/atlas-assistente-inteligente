from __future__ import annotations

import time
from collections import deque
from threading import Event, Lock

from atlas.voice.continuous import ContinuousVoiceListener
from atlas.voice.session import VoiceSession, VoiceState


class FakeSpeech:
    def __init__(self, transcripts: list[str]) -> None:
        self.session = VoiceSession()
        self.microphone_enabled = True
        self._transcripts = deque(transcripts)
        self._lock = Lock()
        self.listen_called = Event()
        self.calls: list[dict[str, object]] = []

    def listen(
        self,
        prompt: str,
        retry_on_failure: bool,
        *,
        timeout: float,
        phrase_time_limit: float,
        verbose: bool,
    ) -> str:
        with self._lock:
            self.calls.append(
                {
                    "prompt": prompt,
                    "retry_on_failure": retry_on_failure,
                    "timeout": timeout,
                    "phrase_time_limit": phrase_time_limit,
                    "verbose": verbose,
                }
            )
            transcript = (
                self._transcripts.popleft()
                if self._transcripts
                else ""
            )

        self.listen_called.set()
        self.session.start_listening()

        if not transcript:
            self.session.complete()
            time.sleep(0.005)
            return ""

        self.session.start_processing(transcript)
        return transcript


def wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if predicate():
            return True

        time.sleep(0.005)

    return bool(predicate())


def test_continuous_voice_executes_only_after_wake_word() -> None:
    speech = FakeSpeech(
        [
            "esta conversa não é um comando",
            "Atlas abra o navegador",
        ]
    )
    commands: list[str] = []
    command_received = Event()

    def receive(command: str) -> None:
        commands.append(command)
        speech.session.complete()
        command_received.set()

    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        receive,
        idle_wait=0.01,
    )

    assert listener.start() is True
    assert command_received.wait(timeout=1) is True
    listener.stop()

    assert commands == ["abra o navegador"]
    assert listener.snapshot().command_count == 1
    assert listener.snapshot().last_command == "abra o navegador"


def test_phrase_without_wake_word_is_ignored_and_completed() -> None:
    speech = FakeSpeech(["abra o navegador"])
    commands: list[str] = []
    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        commands.append,
        idle_wait=0.01,
    )

    listener.start()

    assert wait_until(
        lambda: (
            bool(speech.calls)
            and speech.session.is_state(VoiceState.IDLE)
        )
    )
    listener.stop()

    assert commands == []
    assert listener.snapshot().command_count == 0


def test_listener_waits_while_atlas_is_speaking() -> None:
    speech = FakeSpeech([""])
    speech.session.start_speaking()
    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        lambda command: None,
        idle_wait=0.01,
    )

    listener.start()
    time.sleep(0.04)

    assert speech.calls == []

    speech.session.complete()

    assert speech.listen_called.wait(timeout=1) is True
    listener.stop()


def test_pause_blocks_new_capture_until_resume() -> None:
    speech = FakeSpeech([""])
    speech.session.start_speaking()
    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        lambda command: None,
        idle_wait=0.01,
    )

    listener.start()

    assert listener.pause() is True
    speech.session.complete()
    time.sleep(0.04)

    assert listener.is_paused is True
    assert speech.calls == []
    assert listener.resume() is True
    assert speech.listen_called.wait(timeout=1) is True
    listener.stop()


def test_start_and_stop_are_idempotent() -> None:
    speech = FakeSpeech([""])
    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        lambda command: None,
        idle_wait=0.01,
    )

    assert listener.start() is True
    assert listener.start() is False
    assert listener.stop() is True
    assert listener.stop() is False
    assert listener.snapshot().active is False


def test_disabled_microphone_prevents_continuous_mode() -> None:
    speech = FakeSpeech([])
    speech.microphone_enabled = False
    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        lambda command: None,
    )

    assert listener.start() is False
    assert listener.snapshot().active is False


def test_wake_word_without_command_is_ignored() -> None:
    speech = FakeSpeech(["Atlas"])
    commands: list[str] = []
    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        commands.append,
        idle_wait=0.01,
    )

    listener.start()

    assert wait_until(
        lambda: (
            bool(speech.calls)
            and speech.session.is_state(VoiceState.IDLE)
        )
    )
    listener.stop()

    assert commands == []


def test_callback_failure_is_recorded_without_leaking_state() -> None:
    speech = FakeSpeech(["Atlas abra o navegador"])

    def broken_callback(command: str) -> None:
        raise RuntimeError(f"Falha ao enviar: {command}")

    listener = ContinuousVoiceListener(
        speech,  # type: ignore[arg-type]
        broken_callback,
        idle_wait=0.01,
    )

    listener.start()

    assert wait_until(
        lambda: listener.snapshot().last_error is not None
    )
    listener.stop()

    assert listener.snapshot().last_error == (
        "Falha ao enviar: abra o navegador"
    )
    assert speech.session.is_state(VoiceState.IDLE)


def test_constructor_validates_configuration() -> None:
    speech = FakeSpeech([])

    try:
        ContinuousVoiceListener(
            speech,  # type: ignore[arg-type]
            lambda command: None,
            listen_timeout=0,
        )
    except ValueError as error:
        assert "maior que zero" in str(error)
    else:
        raise AssertionError("Era esperado ValueError.")
