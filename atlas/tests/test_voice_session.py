from __future__ import annotations

from datetime import timezone

import pytest

from atlas.voice.session import (
    VoiceSession,
    VoiceSnapshot,
    VoiceState,
    VoiceTransitionError,
)


def test_session_starts_idle() -> None:
    session = VoiceSession()
    snapshot = session.snapshot()

    assert snapshot.state is VoiceState.IDLE
    assert snapshot.previous_state is None
    assert snapshot.sequence == 0
    assert snapshot.changed_at.tzinfo == timezone.utc
    assert session.interruption_requested() is False


def test_session_runs_complete_voice_lifecycle() -> None:
    session = VoiceSession()

    listening = session.start_listening()
    processing = session.start_processing("  abra o navegador  ")
    speaking = session.start_speaking()
    completed = session.complete()

    assert listening.state is VoiceState.LISTENING
    assert processing.state is VoiceState.PROCESSING
    assert processing.last_transcript == "abra o navegador"
    assert speaking.state is VoiceState.SPEAKING
    assert completed.state is VoiceState.IDLE
    assert completed.previous_state is VoiceState.SPEAKING
    assert completed.sequence == 4


def test_session_rejects_invalid_transition() -> None:
    session = VoiceSession()
    session.start_speaking()

    with pytest.raises(VoiceTransitionError) as exc_info:
        session.start_processing("comando tardio")

    error = exc_info.value
    assert error.current_state is VoiceState.SPEAKING
    assert error.requested_state is VoiceState.PROCESSING


def test_interruption_is_idempotent_and_auditable() -> None:
    session = VoiceSession()
    session.start_speaking()

    first_change = session.interrupt("Solicitado pelo usuário")
    first_snapshot = session.snapshot()
    second_change = session.interrupt("Outro motivo")

    assert first_change is True
    assert second_change is False
    assert first_snapshot.state is VoiceState.INTERRUPTED
    assert first_snapshot.interruption_reason == "Solicitado pelo usuário"
    assert session.interruption_requested() is True
    assert session.wait_for_interruption(timeout=0.001) is True


def test_new_listening_cycle_clears_previous_interruption() -> None:
    session = VoiceSession()
    session.interrupt("Parar")

    snapshot = session.start_listening()

    assert snapshot.state is VoiceState.LISTENING
    assert snapshot.interruption_reason is None
    assert session.interruption_requested() is False


def test_failure_can_recover_to_idle() -> None:
    session = VoiceSession()
    session.start_listening()

    failed = session.fail(RuntimeError("Microfone indisponível"))
    recovered = session.complete()

    assert failed.state is VoiceState.ERROR
    assert failed.error_message == "Microfone indisponível"
    assert recovered.state is VoiceState.IDLE


def test_error_state_can_announce_failure() -> None:
    session = VoiceSession()
    session.fail("Serviço indisponível")

    speaking = session.start_speaking()

    assert speaking.state is VoiceState.SPEAKING
    assert speaking.error_message == "Serviço indisponível"


def test_subscribers_receive_immutable_snapshots() -> None:
    session = VoiceSession()
    received: list[VoiceSnapshot] = []

    session.subscribe(received.append)
    session.start_listening()
    session.start_processing("pesquise Atlas")

    assert [snapshot.state for snapshot in received] == [
        VoiceState.LISTENING,
        VoiceState.PROCESSING,
    ]
    assert received[-1].last_transcript == "pesquise Atlas"
    assert session.unsubscribe(received.append) is True


def test_listener_failure_does_not_break_voice_cycle() -> None:
    session = VoiceSession()

    def broken_listener(snapshot: VoiceSnapshot) -> None:
        raise RuntimeError(snapshot.state.value)

    session.subscribe(broken_listener)

    snapshot = session.start_listening()

    assert snapshot.state is VoiceState.LISTENING


def test_wait_for_state_and_timeout_validation() -> None:
    session = VoiceSession()

    assert session.wait_for_state(VoiceState.IDLE, timeout=0.001) is True
    assert (
        session.wait_for_state(
            VoiceState.SPEAKING,
            timeout=0.001,
        )
        is False
    )

    with pytest.raises(ValueError, match="não pode ser negativo"):
        session.wait_for_state(VoiceState.IDLE, timeout=-1)

    with pytest.raises(ValueError, match="não pode ser negativo"):
        session.wait_for_interruption(timeout=-1)


def test_reset_clears_cycle_metadata() -> None:
    session = VoiceSession()
    session.start_listening()
    session.start_processing("comando")
    session.interrupt("cancelado")

    snapshot = session.reset()

    assert snapshot.state is VoiceState.IDLE
    assert snapshot.last_transcript is None
    assert snapshot.interruption_reason is None
    assert snapshot.error_message is None
    assert session.interruption_requested() is False


def test_snapshot_is_serializable() -> None:
    session = VoiceSession()
    session.start_listening()
    session.start_processing("abrir CRM")

    serialized = session.snapshot().as_dict()

    assert serialized["state"] == "processing"
    assert serialized["previous_state"] == "listening"
    assert serialized["last_transcript"] == "abrir CRM"
    assert isinstance(serialized["changed_at"], str)
