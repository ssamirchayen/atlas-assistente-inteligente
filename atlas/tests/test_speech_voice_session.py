from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import speech_recognition as sr

from atlas.voice.session import VoiceSession, VoiceState
from atlas.voice.speech import SpeechInterface


def make_speech() -> tuple[SpeechInterface, VoiceSession]:
    session = VoiceSession()
    speech = SpeechInterface(
        microphone_enabled=True,
        session=session,
        tts_provider="windows",
    )
    speech.recognizer = MagicMock()
    speech.interruption_recognizer = MagicMock()
    speech._microphone_calibrated = True
    return speech, session


def microphone_context() -> MagicMock:
    context = MagicMock()
    context.__enter__.return_value = MagicMock()
    return context


def test_speech_uses_shared_voice_session() -> None:
    session = VoiceSession()

    speech = SpeechInterface(session=session)

    assert speech.session is session


def test_interruption_recognizer_preserves_natural_command_pause() -> None:
    speech = SpeechInterface(microphone_enabled=False)

    assert speech.interruption_recognizer.pause_threshold == 1.2
    assert speech.interruption_recognizer.non_speaking_duration == 0.6


def test_neural_voice_is_used_when_configured() -> None:
    session = VoiceSession()
    speech = SpeechInterface(
        microphone_enabled=False,
        session=session,
        tts_provider="edge",
    )

    with (
        patch("atlas.voice.speech.VOICE_ENABLED", True),
        patch.object(
            speech,
            "_speak_with_neural_voice",
            return_value=True,
        ) as neural_voice,
        patch.object(speech, "_speak_with_windows_voice") as local_voice,
    ):
        speech.say("Olá, Ssamir")

    neural_voice.assert_called_once_with("Olá, Ssamir")
    local_voice.assert_not_called()
    assert session.state is VoiceState.IDLE


def test_neural_voice_failure_uses_windows_fallback() -> None:
    session = VoiceSession()
    speech = SpeechInterface(
        microphone_enabled=False,
        session=session,
        tts_provider="edge",
    )

    with (
        patch("atlas.voice.speech.VOICE_ENABLED", True),
        patch.object(
            speech,
            "_speak_with_neural_voice",
            return_value=False,
        ) as neural_voice,
        patch.object(
            speech,
            "_speak_with_windows_voice",
            return_value=True,
        ) as local_voice,
    ):
        speech.say("Resposta com fallback")

    neural_voice.assert_called_once_with("Resposta com fallback")
    local_voice.assert_called_once_with("Resposta com fallback")
    assert session.state is VoiceState.IDLE


def test_successful_listening_finishes_in_processing_state() -> None:
    speech, session = make_speech()
    speech.recognizer.recognize_google.return_value = " abra o navegador "

    with patch(
        "atlas.voice.speech.sr.Microphone",
        return_value=microphone_context(),
    ):
        transcript = speech.listen()

    assert transcript == "abra o navegador"
    assert session.state is VoiceState.PROCESSING
    assert session.snapshot().last_transcript == "abra o navegador"


def test_listening_timeout_returns_session_to_idle() -> None:
    speech, session = make_speech()
    speech.recognizer.listen.side_effect = sr.WaitTimeoutError()

    with patch(
        "atlas.voice.speech.sr.Microphone",
        return_value=microphone_context(),
    ):
        transcript = speech.listen()

    assert transcript == ""
    assert session.state is VoiceState.IDLE


def test_microphone_error_is_reported_to_session() -> None:
    speech, session = make_speech()

    with patch(
        "atlas.voice.speech.sr.Microphone",
        side_effect=OSError("Dispositivo ocupado"),
    ):
        transcript = speech.listen()

    assert transcript == ""
    assert session.state is VoiceState.ERROR
    assert session.snapshot().error_message == "Dispositivo ocupado"
    assert speech.microphone_enabled is False


def test_speaking_reports_state_and_returns_to_idle() -> None:
    speech, session = make_speech()
    observed_states: list[VoiceState] = []
    session.subscribe(
        lambda snapshot: observed_states.append(snapshot.state)
    )

    with (
        patch("atlas.voice.speech.VOICE_ENABLED", True),
        patch("atlas.voice.speech.subprocess.Popen") as popen,
    ):
        process = popen.return_value
        process.wait.return_value = 0
        speech.say("Operação concluída")

    assert observed_states == [
        VoiceState.SPEAKING,
        VoiceState.IDLE,
    ]
    assert session.state is VoiceState.IDLE
    popen.assert_called_once()
    process.wait.assert_called_once_with(timeout=20)


def test_disabled_voice_still_completes_state_cycle() -> None:
    speech, session = make_speech()

    with (
        patch("atlas.voice.speech.VOICE_ENABLED", False),
        patch("atlas.voice.speech.subprocess.Popen") as popen,
    ):
        speech.say("Resposta em texto")

    assert session.state is VoiceState.IDLE
    popen.assert_not_called()


def test_pending_interruption_prevents_new_speech() -> None:
    speech, session = make_speech()
    session.interrupt("Usuário pediu silêncio")

    with patch("atlas.voice.speech.subprocess.Popen") as popen:
        speech.say("Esta mensagem não deve ser falada")

    assert session.state is VoiceState.INTERRUPTED
    popen.assert_not_called()


def test_request_interruption_is_forwarded_to_session() -> None:
    speech, session = make_speech()
    session.start_speaking()

    changed = speech.request_interruption("Nova ordem recebida")

    assert changed is True
    assert session.state is VoiceState.INTERRUPTED
    assert session.interruption_requested() is True


def test_request_interruption_terminates_active_speech_process() -> None:
    speech, session = make_speech()
    process = MagicMock()
    process.poll.return_value = None
    process.wait.return_value = 0
    speech._speech_process = process
    session.start_speaking()

    changed = speech.request_interruption("Atlas, pare")

    assert changed is True
    assert session.state is VoiceState.INTERRUPTED
    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=0.75)


def test_recognition_service_error_is_announced_and_completes() -> None:
    speech, session = make_speech()
    observed_states: list[VoiceState] = []
    session.subscribe(
        lambda snapshot: observed_states.append(snapshot.state)
    )
    speech.recognizer.recognize_google.side_effect = sr.RequestError(
        "sem conexão"
    )

    with (
        patch(
            "atlas.voice.speech.sr.Microphone",
            return_value=microphone_context(),
        ),
        patch("atlas.voice.speech.VOICE_ENABLED", False),
    ):
        transcript = speech.listen()

    assert transcript == ""
    assert VoiceState.ERROR in observed_states
    assert VoiceState.SPEAKING in observed_states
    assert session.state is VoiceState.IDLE


def test_listening_limits_are_forwarded_to_recognizer() -> None:
    speech, _ = make_speech()
    speech.recognizer.recognize_google.return_value = "Atlas abrir CRM"
    microphone = microphone_context()
    source = microphone.__enter__.return_value

    with patch(
        "atlas.voice.speech.sr.Microphone",
        return_value=microphone,
    ):
        transcript = speech.listen(
            timeout=2.5,
            phrase_time_limit=12,
        )

    assert transcript == "Atlas abrir CRM"
    speech.recognizer.listen.assert_called_once_with(
        source,
        timeout=2.5,
        phrase_time_limit=12,
    )


def test_interruption_capture_preserves_voice_session_state() -> None:
    speech, session = make_speech()
    speech.interruption_recognizer.recognize_google.return_value = (
        "Atlas pare"
    )
    microphone = microphone_context()
    source = microphone.__enter__.return_value
    session.start_speaking()

    with patch(
        "atlas.voice.speech.sr.Microphone",
        return_value=microphone,
    ):
        transcript = speech.listen_for_interruption(
            timeout=1.5,
            phrase_time_limit=4,
        )

    assert transcript == "Atlas pare"
    assert session.state is VoiceState.SPEAKING
    speech.interruption_recognizer.listen.assert_called_once_with(
        source,
        timeout=1.5,
        phrase_time_limit=4,
    )


def test_interruption_timeout_preserves_voice_session_state() -> None:
    speech, session = make_speech()
    speech.interruption_recognizer.listen.side_effect = (
        sr.WaitTimeoutError()
    )
    session.start_processing("comando em execução")

    with patch(
        "atlas.voice.speech.sr.Microphone",
        return_value=microphone_context(),
    ):
        transcript = speech.listen_for_interruption()

    assert transcript == ""
    assert session.state is VoiceState.PROCESSING


def test_interruption_capture_returns_all_recognition_alternatives() -> None:
    speech, session = make_speech()
    speech.interruption_recognizer.recognize_google.return_value = {
        "alternative": [
            {"transcript": "texto reproduzido pelo Atlas"},
            {"transcript": "texto reproduzido Atlas pare"},
            {"transcript": "texto reproduzido Atlas para"},
        ]
    }
    session.start_speaking()

    with patch(
        "atlas.voice.speech.sr.Microphone",
        return_value=microphone_context(),
    ):
        transcript = speech.listen_for_interruption()

    assert transcript.splitlines() == [
        "texto reproduzido pelo Atlas",
        "texto reproduzido Atlas pare",
        "texto reproduzido Atlas para",
    ]
    assert session.state is VoiceState.SPEAKING


@pytest.mark.parametrize(
    ("timeout", "phrase_time_limit"),
    [
        (0, 10),
        (1, 0),
        (-1, 10),
        (1, -1),
    ],
)
def test_listening_limits_must_be_positive(
    timeout: float,
    phrase_time_limit: float,
) -> None:
    speech, session = make_speech()

    with pytest.raises(ValueError, match="maior que zero"):
        speech.listen(
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )

    assert session.state is VoiceState.IDLE
