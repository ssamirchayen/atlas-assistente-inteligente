from __future__ import annotations

from dataclasses import dataclass

import pytest

from atlas.voice.latency import VoiceCycleOutcome, VoiceLatencyTracker
from atlas.voice.session import VoiceSession


@dataclass
class FakeClock:
    value: float = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_latency_tracker_measures_complete_voice_cycle() -> None:
    clock = FakeClock()
    session = VoiceSession()
    tracker = VoiceLatencyTracker(session, clock=clock)

    session.start_listening()
    clock.advance(0.4)
    session.start_processing("abra o navegador")
    clock.advance(0.6)
    session.start_speaking()
    clock.advance(0.8)
    session.complete()

    record = tracker.latest()

    assert record is not None
    assert record.outcome is VoiceCycleOutcome.COMPLETED
    assert record.recognized is True
    assert record.listening_ms == pytest.approx(400)
    assert record.processing_ms == pytest.approx(600)
    assert record.speaking_ms == pytest.approx(800)
    assert record.total_ms == pytest.approx(1800)


def test_latency_record_never_contains_transcript() -> None:
    clock = FakeClock()
    session = VoiceSession()
    tracker = VoiceLatencyTracker(session, clock=clock)
    secret_transcript = "minha senha é segredo"

    session.start_listening()
    clock.advance(0.1)
    session.start_processing(secret_transcript)
    clock.advance(0.1)
    session.complete()

    record = tracker.latest()

    assert record is not None
    serialized = record.as_dict()
    assert "transcript" not in serialized
    assert secret_transcript not in str(serialized)


def test_interrupted_cycle_is_counted_without_completion() -> None:
    clock = FakeClock()
    session = VoiceSession()
    tracker = VoiceLatencyTracker(session, clock=clock)

    session.start_listening()
    clock.advance(0.25)
    session.interrupt("usuário pediu para parar")

    record = tracker.latest()

    assert record is not None
    assert record.outcome is VoiceCycleOutcome.INTERRUPTED
    assert record.total_ms == pytest.approx(250)
    assert tracker.summary()["interrupted"] == 1


def test_error_cycle_is_counted() -> None:
    clock = FakeClock()
    session = VoiceSession()
    tracker = VoiceLatencyTracker(session, clock=clock)

    session.start_listening()
    clock.advance(0.2)
    session.fail("microfone indisponível")

    assert tracker.summary() == {
        "cycles": 1,
        "completed": 0,
        "interrupted": 0,
        "errors": 1,
        "average_total_ms": 200.0,
        "maximum_total_ms": 200.0,
    }


def test_history_is_bounded_and_summary_uses_retained_cycles() -> None:
    clock = FakeClock()
    session = VoiceSession()
    tracker = VoiceLatencyTracker(
        session,
        history_limit=2,
        clock=clock,
    )

    for duration in (0.1, 0.2, 0.3):
        session.start_listening()
        clock.advance(duration)
        session.complete()

    assert [record.sequence for record in tracker.history()] == [2, 3]
    assert tracker.summary()["average_total_ms"] == 250.0
    assert tracker.summary()["maximum_total_ms"] == 300.0


def test_tracker_close_is_idempotent() -> None:
    session = VoiceSession()
    tracker = VoiceLatencyTracker(session)

    assert tracker.close() is True
    assert tracker.close() is False

    session.start_listening()
    session.complete()
    assert tracker.history() == ()


def test_tracker_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="positivo"):
        VoiceLatencyTracker(VoiceSession(), history_limit=0)
