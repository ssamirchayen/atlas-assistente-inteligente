from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, RLock, Thread, current_thread
from time import monotonic
from typing import TYPE_CHECKING

from atlas.core.config import ATLAS_NAME
from atlas.utils.text import normalize

if TYPE_CHECKING:
    from atlas.voice.speech import SpeechInterface


@dataclass(frozen=True, slots=True)
class VoiceInterruptionIntent:
    """Solicitação de interrupção reconhecida pelo monitor de voz."""

    transcript: str
    command: str
    cancel_execution: bool


@dataclass(frozen=True, slots=True)
class VoiceInterruptionSnapshot:
    """Estado imutável do monitor de interrupções."""

    active: bool
    armed: bool
    interruption_count: int
    last_intent: VoiceInterruptionIntent | None
    last_error: str | None


def detect_voice_interruption(
    transcript: str,
    wake_word: str = ATLAS_NAME,
    *,
    allow_without_wake: bool = False,
) -> VoiceInterruptionIntent | None:
    """Localiza um comando de parada entre hipóteses e áudio de eco."""

    wake_variations = _wake_variations(wake_word)
    wake_expression = "|".join(
        re.escape(variation)
        for variation in wake_variations
        if variation
    )
    wake_pattern = re.compile(rf"\b(?:{wake_expression})\b")

    matched_transcript = ""
    command = ""

    for candidate in str(transcript).splitlines():
        normalized_candidate = normalize(candidate)

        if allow_without_wake and _is_stop_command(normalized_candidate):
            matched_transcript = candidate.strip()
            command = normalized_candidate
            break

        for match in wake_pattern.finditer(normalized_candidate):
            possible_command = normalized_candidate[match.end() :].strip()

            if _is_stop_command(possible_command):
                matched_transcript = candidate.strip()
                command = possible_command
                break

        if command:
            break

    if not command:
        return None

    cancel_markers = (
        "cancel",
        "interromp",
        "execucao",
        "processamento",
        "workflow",
        "comando",
        "tarefa",
    )

    return VoiceInterruptionIntent(
        transcript=matched_transcript,
        command=command,
        cancel_execution=any(
            marker in command for marker in cancel_markers
        ),
    )


def _wake_variations(wake_word: str) -> set[str]:
    """Retorna variações comuns produzidas pelo reconhecimento pt-BR."""

    return {
        normalize(wake_word),
        "atlas",
        "atras",
        "atla",
        "athos",
        "atho",
    }


def _contains_wake_word(transcript: str, wake_word: str) -> bool:
    variations = _wake_variations(wake_word)
    expression = "|".join(
        re.escape(variation) for variation in variations if variation
    )

    if not expression:
        return False

    pattern = re.compile(rf"\b(?:{expression})\b")
    return any(
        pattern.search(normalize(candidate)) is not None
        for candidate in str(transcript).splitlines()
    )


def _is_stop_command(command: str) -> bool:
    exact_commands = {
        "pare",
        "para",
        "parar",
        "silencio",
        "chega",
        "cala a boca",
    }

    if command in exact_commands:
        return True

    stop_prefixes = (
        "pare ",
        "parar ",
        "silencio ",
        "fique em silencio",
        "cala a boca",
        "chega ",
        "cancele",
        "cancelar",
        "interrompa",
        "interromper",
        "pode parar",
        "para de falar",
        "para ai",
        "para agora",
    )
    return command.startswith(stop_prefixes)


class VoiceInterruptionMonitor:
    """
    Escuta apenas durante uma execução ou fala ativa do Atlas.

    O monitor usa uma captura curta e independente da ``VoiceSession``.
    Assim, ele consegue ouvir ``Atlas, pare`` sem sobrescrever o estado
    ``PROCESSING`` ou ``SPEAKING`` que precisa interromper.
    """

    def __init__(
        self,
        speech: SpeechInterface,
        on_interruption: Callable[[VoiceInterruptionIntent], None],
        *,
        wake_word: str = ATLAS_NAME,
        listen_timeout: float = 1.25,
        phrase_time_limit: float = 4.0,
        idle_wait: float = 0.1,
        wake_followup_timeout: float = 4.0,
    ) -> None:
        if not callable(on_interruption):
            raise TypeError("O receptor de interrupções deve ser chamável.")
        if listen_timeout <= 0:
            raise ValueError("O tempo de escuta deve ser maior que zero.")
        if phrase_time_limit <= 0:
            raise ValueError("O limite da frase deve ser maior que zero.")
        if idle_wait <= 0:
            raise ValueError("O intervalo de espera deve ser maior que zero.")
        if wake_followup_timeout <= 0:
            raise ValueError(
                "O tempo para completar a interrupção deve ser maior que zero."
            )

        normalized_wake_word = str(wake_word).strip()

        if not normalized_wake_word:
            raise ValueError("A palavra de ativação não pode ser vazia.")

        self.speech = speech
        self.on_interruption = on_interruption
        self.wake_word = normalized_wake_word
        self.listen_timeout = float(listen_timeout)
        self.phrase_time_limit = float(phrase_time_limit)
        self.idle_wait = float(idle_wait)
        self.wake_followup_timeout = float(wake_followup_timeout)

        self._lock = RLock()
        self._stop_event = Event()
        self._armed_event = Event()
        self._thread: Thread | None = None
        self._active = False
        self._interruption_count = 0
        self._last_intent: VoiceInterruptionIntent | None = None
        self._last_error: str | None = None
        self._wake_pending_until = 0.0

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active and not self._stop_event.is_set()

    @property
    def is_armed(self) -> bool:
        return self.is_active and self._armed_event.is_set()

    @property
    def has_pending_wake_word(self) -> bool:
        """Indica se um ``Atlas`` isolado ainda aguarda o comando final."""

        with self._lock:
            return self._wake_pending_until > monotonic()

    def start(self) -> bool:
        """Inicia a thread ociosa do monitor."""

        with self._lock:
            if self._active and not self._stop_event.is_set():
                return False

            if not self.speech.microphone_enabled:
                return False

            self._stop_event.clear()
            self._armed_event.clear()
            self._last_error = None
            self._wake_pending_until = 0.0
            self._active = True
            self._thread = Thread(
                target=self._run,
                name="atlas-voice-interruption",
                daemon=True,
            )
            thread = self._thread

        thread.start()
        return True

    def stop(
        self,
        *,
        wait: bool = True,
        timeout: float = 2.0,
    ) -> bool:
        if timeout < 0:
            raise ValueError("O tempo de parada não pode ser negativo.")

        with self._lock:
            was_active = self._active and not self._stop_event.is_set()
            self._active = False
            self._armed_event.clear()
            self._wake_pending_until = 0.0
            self._stop_event.set()
            thread = self._thread

        if (
            wait
            and thread is not None
            and thread is not current_thread()
        ):
            thread.join(timeout=timeout)

        return was_active

    def arm(self) -> bool:
        """Habilita a captura temporária de frases de interrupção."""

        if not self.is_active:
            return False

        self._armed_event.set()
        return True

    def disarm(self) -> bool:
        """Suspende a captura sem encerrar o monitor."""

        was_armed = self._armed_event.is_set()
        self._armed_event.clear()
        self._clear_pending_wake_word()
        return was_armed

    def snapshot(self) -> VoiceInterruptionSnapshot:
        with self._lock:
            return VoiceInterruptionSnapshot(
                active=(
                    self._active and not self._stop_event.is_set()
                ),
                armed=(
                    self._active
                    and not self._stop_event.is_set()
                    and self._armed_event.is_set()
                ),
                interruption_count=self._interruption_count,
                last_intent=self._last_intent,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        try:
            while self.is_active:
                if not self._armed_event.wait(self.idle_wait):
                    continue

                if not self.speech.microphone_enabled:
                    self._stop_event.wait(self.idle_wait)
                    continue

                transcript = self.speech.listen_for_interruption(
                    timeout=self.listen_timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )

                if not self.is_active or not self._armed_event.is_set():
                    continue

                intent = detect_voice_interruption(
                    transcript,
                    self.wake_word,
                )

                wake_detected = _contains_wake_word(
                    transcript,
                    self.wake_word,
                )

                if intent is None and (
                    self.has_pending_wake_word or wake_detected
                ):
                    intent = detect_voice_interruption(
                        transcript,
                        self.wake_word,
                        allow_without_wake=True,
                    )

                if intent is None:
                    if wake_detected:
                        self._remember_wake_word()
                        self._report_pending_wake_word(transcript)
                    continue

                self._clear_pending_wake_word()
                self._record_intent(intent)
                self.disarm()
                print(
                    "[VOZ] Interrupção reconhecida: "
                    f"{intent.command}"
                )

                try:
                    self.on_interruption(intent)
                except Exception as exc:
                    self._record_error(exc)

        except Exception as exc:
            self._record_error(exc)

        finally:
            with self._lock:
                self._active = False
                self._thread = None

    def _record_intent(self, intent: VoiceInterruptionIntent) -> None:
        with self._lock:
            self._interruption_count += 1
            self._last_intent = intent

    def _remember_wake_word(self) -> None:
        with self._lock:
            self._wake_pending_until = (
                monotonic() + self.wake_followup_timeout
            )

    def _clear_pending_wake_word(self) -> None:
        with self._lock:
            self._wake_pending_until = 0.0

    @staticmethod
    def _report_pending_wake_word(transcript: str) -> None:
        compact = " | ".join(
            line.strip()
            for line in transcript.splitlines()
            if line.strip()
        )
        print(
            "[VOZ] Palavra de ativação reconhecida; aguardando "
            f"'pare': {compact}"
        )

    def _record_error(self, error: Exception) -> None:
        message = str(error).strip() or type(error).__name__

        with self._lock:
            self._last_error = message
