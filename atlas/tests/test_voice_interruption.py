from __future__ import annotations

import time
from collections import deque
from threading import Event, Lock

import pytest

from atlas.voice.interruption import (
    VoiceInterruptionIntent,
    VoiceInterruptionMonitor,
    detect_voice_interruption,
)


class FakeInterruptionSpeech:
    def __init__(self, transcripts: list[str]) -> None:
        self.microphone_enabled = True
        self._transcripts = deque(transcripts)
        self._lock = Lock()
        self.listen_called = Event()
        self.calls = 0

    def listen_for_interruption(
        self,
        *,
        timeout: float,
        phrase_time_limit: float,
    ) -> str:
        del timeout, phrase_time_limit

        with self._lock:
            self.calls += 1
            transcript = (
                self._transcripts.popleft()
                if self._transcripts
                else ""
            )

        self.listen_called.set()
        time.sleep(0.005)
        return transcript


def wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if predicate():
            return True

        time.sleep(0.005)

    return bool(predicate())


@pytest.mark.parametrize(
    ("transcript", "command", "cancel_execution"),
    [
        ("Atlas pare", "pare", False),
        ("Atlas, pare de falar", "pare de falar", False),
        ("Atlas para", "para", False),
        ("Atras silêncio", "silencio", False),
        ("Ok Atlas cancele a execução", "cancele a execucao", True),
        ("Atlas interrompa o workflow", "interrompa o workflow", True),
        (
            "A pesquisa foi concluída e o resultado abriu Atlas pare",
            "pare",
            False,
        ),
        (
            "Resposta capturada\ntexto do alto-falante Atlas para",
            "para",
            False,
        ),
    ],
)
def test_detects_supported_interruption_phrases(
    transcript: str,
    command: str,
    cancel_execution: bool,
) -> None:
    intent = detect_voice_interruption(transcript)

    assert intent is not None
    assert intent.command == command
    assert intent.cancel_execution is cancel_execution


@pytest.mark.parametrize(
    "transcript",
    [
        "pare",
        "conversa normal",
        "Atlas abra o navegador",
        "Atlas pesquise carros usados",
        "Atlas para Manaus",
        "Atlas foi criado para empresas",
        "Atlas",
    ],
)
def test_ignores_phrases_that_are_not_interruptions(
    transcript: str,
) -> None:
    assert detect_voice_interruption(transcript) is None


@pytest.mark.parametrize(
    ("transcript", "expected_command"),
    [
        ("pare", "pare"),
        ("pare agora", "pare agora"),
        ("silêncio", "silencio"),
    ],
)
def test_detects_followup_command_after_pending_wake_word(
    transcript: str,
    expected_command: str,
) -> None:
    intent = detect_voice_interruption(
        transcript,
        allow_without_wake=True,
    )

    assert intent is not None
    assert intent.command == expected_command


def test_monitor_combines_wake_word_and_stop_in_two_captures() -> None:
    speech = FakeInterruptionSpeech(["Atlas", "pare"])
    intents: list[VoiceInterruptionIntent] = []
    received = Event()

    def receive(intent: VoiceInterruptionIntent) -> None:
        intents.append(intent)
        received.set()

    listener = VoiceInterruptionMonitor(
        speech,  # type: ignore[arg-type]
        receive,
        idle_wait=0.01,
    )

    listener.start()
    listener.arm()

    assert received.wait(timeout=1) is True
    listener.stop()

    assert [intent.command for intent in intents] == ["pare"]
    assert listener.snapshot().interruption_count == 1


def test_monitor_combines_alternatives_from_same_recognition() -> None:
    speech = FakeInterruptionSpeech(["atla\nAtlas\nAthos\npare"])
    intents: list[VoiceInterruptionIntent] = []
    received = Event()

    def receive(intent: VoiceInterruptionIntent) -> None:
        intents.append(intent)
        received.set()

    listener = VoiceInterruptionMonitor(
        speech,  # type: ignore[arg-type]
        receive,
        idle_wait=0.01,
    )

    listener.start()
    listener.arm()

    assert received.wait(timeout=1) is True
    listener.stop()

    assert [intent.command for intent in intents] == ["pare"]


def test_monitor_stays_idle_until_armed() -> None:
    speech = FakeInterruptionSpeech(["Atlas pare"])
    received = Event()
    listener = VoiceInterruptionMonitor(
        speech,  # type: ignore[arg-type]
        lambda intent: received.set(),
        idle_wait=0.01,
    )

    listener.start()
    time.sleep(0.04)

    assert speech.calls == 0

    assert listener.arm() is True
    assert received.wait(timeout=1) is True
    listener.stop()


def test_monitor_emits_interruption_and_disarms() -> None:
    speech = FakeInterruptionSpeech(
        ["Atlas abra o navegador", "Atlas pare"]
    )
    intents: list[VoiceInterruptionIntent] = []
    received = Event()

    def receive(intent: VoiceInterruptionIntent) -> None:
        intents.append(intent)
        received.set()

    listener = VoiceInterruptionMonitor(
        speech,  # type: ignore[arg-type]
        receive,
        idle_wait=0.01,
    )

    listener.start()
    listener.arm()

    assert received.wait(timeout=1) is True
    assert wait_until(lambda: not listener.is_armed)
    listener.stop()

    assert [intent.command for intent in intents] == ["pare"]
    assert listener.snapshot().interruption_count == 1


def test_start_stop_and_arm_are_idempotent() -> None:
    speech = FakeInterruptionSpeech([])
    listener = VoiceInterruptionMonitor(
        speech,  # type: ignore[arg-type]
        lambda intent: None,
        idle_wait=0.01,
    )

    assert listener.start() is True
    assert listener.start() is False
    assert listener.arm() is True
    assert listener.disarm() is True
    assert listener.disarm() is False
    assert listener.stop() is True
    assert listener.stop() is False


def test_disabled_microphone_prevents_monitor_start() -> None:
    speech = FakeInterruptionSpeech([])
    speech.microphone_enabled = False
    listener = VoiceInterruptionMonitor(
        speech,  # type: ignore[arg-type]
        lambda intent: None,
    )

    assert listener.start() is False
    assert listener.arm() is False


def test_callback_failure_is_auditable() -> None:
    speech = FakeInterruptionSpeech(["Atlas pare"])

    def broken_callback(intent: VoiceInterruptionIntent) -> None:
        raise RuntimeError(f"Falha no callback: {intent.command}")

    listener = VoiceInterruptionMonitor(
        speech,  # type: ignore[arg-type]
        broken_callback,
        idle_wait=0.01,
    )

    listener.start()
    listener.arm()

    assert wait_until(
        lambda: listener.snapshot().last_error is not None
    )
    listener.stop()

    assert listener.snapshot().last_error == "Falha no callback: pare"


def test_constructor_validates_configuration() -> None:
    speech = FakeInterruptionSpeech([])

    with pytest.raises(ValueError, match="maior que zero"):
        VoiceInterruptionMonitor(
            speech,  # type: ignore[arg-type]
            lambda intent: None,
            phrase_time_limit=0,
        )

    with pytest.raises(ValueError, match="maior que zero"):
        VoiceInterruptionMonitor(
            speech,  # type: ignore[arg-type]
            lambda intent: None,
            wake_followup_timeout=0,
        )
