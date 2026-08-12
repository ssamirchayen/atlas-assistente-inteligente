from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, RLock, Thread, current_thread

from atlas.core.config import ATLAS_NAME
from atlas.utils.text import remove_wake_word
from atlas.voice.session import VoiceState
from atlas.voice.speech import SpeechInterface


@dataclass(frozen=True, slots=True)
class ContinuousVoiceSnapshot:
    """Estado observável da escuta contínua."""

    active: bool
    paused: bool
    command_count: int
    last_command: str | None
    last_error: str | None


class ContinuousVoiceListener:
    """
    Mantém o microfone aguardando a palavra de ativação em uma thread.

    Apenas frases iniciadas por ``Atlas`` (ou uma variação reconhecida)
    são encaminhadas. A escuta aguarda a sessão retornar a ``IDLE`` antes
    de abrir um novo ciclo, impedindo que o Atlas reconheça a própria voz.
    """

    def __init__(
        self,
        speech: SpeechInterface,
        on_command: Callable[[str], None],
        *,
        wake_word: str = ATLAS_NAME,
        listen_timeout: float = 2.0,
        phrase_time_limit: float = 15.0,
        idle_wait: float = 0.1,
    ) -> None:
        if not callable(on_command):
            raise TypeError("O receptor de comandos deve ser chamável.")
        if listen_timeout <= 0:
            raise ValueError("O tempo de escuta deve ser maior que zero.")
        if phrase_time_limit <= 0:
            raise ValueError("O limite da frase deve ser maior que zero.")
        if idle_wait <= 0:
            raise ValueError("O intervalo de espera deve ser maior que zero.")

        normalized_wake_word = str(wake_word).strip()

        if not normalized_wake_word:
            raise ValueError("A palavra de ativação não pode ser vazia.")

        self.speech = speech
        self.session = speech.session
        self.on_command = on_command
        self.wake_word = normalized_wake_word
        self.listen_timeout = float(listen_timeout)
        self.phrase_time_limit = float(phrase_time_limit)
        self.idle_wait = float(idle_wait)

        self._lock = RLock()
        self._stop_event = Event()
        self._pause_event = Event()
        self._thread: Thread | None = None
        self._active = False
        self._command_count = 0
        self._last_command: str | None = None
        self._last_error: str | None = None

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active and not self._stop_event.is_set()

    @property
    def is_paused(self) -> bool:
        return self.is_active and self._pause_event.is_set()

    def start(self) -> bool:
        """Ativa a escuta. Retorna ``False`` quando ela já está ativa."""

        with self._lock:
            if self._active and not self._stop_event.is_set():
                return False

            if not self.speech.microphone_enabled:
                return False

            self._stop_event.clear()
            self._pause_event.clear()
            self._last_error = None
            self._active = True
            self._thread = Thread(
                target=self._run,
                name="atlas-continuous-voice",
                daemon=True,
            )
            thread = self._thread

        thread.start()
        return True

    def stop(
        self,
        *,
        wait: bool = True,
        timeout: float = 3.0,
    ) -> bool:
        """Solicita a parada cooperativa da escuta contínua."""

        if timeout < 0:
            raise ValueError("O tempo de parada não pode ser negativo.")

        with self._lock:
            was_active = self._active and not self._stop_event.is_set()
            self._active = False
            self._stop_event.set()
            self._pause_event.clear()
            thread = self._thread

        if (
            wait
            and thread is not None
            and thread is not current_thread()
        ):
            thread.join(timeout=timeout)

        return was_active

    def pause(self) -> bool:
        """Pausa novas capturas sem encerrar a thread."""

        if not self.is_active:
            return False

        self._pause_event.set()
        return True

    def resume(self) -> bool:
        """Retoma novas capturas após processamento ou síntese de voz."""

        if not self.is_active:
            return False

        self._pause_event.clear()
        return True

    def snapshot(self) -> ContinuousVoiceSnapshot:
        with self._lock:
            return ContinuousVoiceSnapshot(
                active=(
                    self._active and not self._stop_event.is_set()
                ),
                paused=(
                    self._active
                    and not self._stop_event.is_set()
                    and self._pause_event.is_set()
                ),
                command_count=self._command_count,
                last_command=self._last_command,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        try:
            while self.is_active:
                if self._wait_while_paused():
                    break

                if not self.speech.microphone_enabled:
                    break

                if not self.session.is_state(VoiceState.IDLE):
                    self.session.wait_for_state(
                        VoiceState.IDLE,
                        timeout=self.idle_wait,
                    )
                    continue

                transcript = self.speech.listen(
                    prompt="",
                    retry_on_failure=False,
                    timeout=self.listen_timeout,
                    phrase_time_limit=self.phrase_time_limit,
                    verbose=False,
                )

                if not self.is_active or self._pause_event.is_set():
                    self._complete_unhandled_cycle()
                    continue

                if not transcript:
                    continue

                activated, command = remove_wake_word(
                    transcript,
                    self.wake_word,
                )

                if not activated or not command:
                    self._complete_unhandled_cycle()
                    continue

                self._record_command(command)
                print(f"[VOZ CONTÍNUA] Comando recebido: {command}")

                try:
                    self.on_command(command)
                except Exception as exc:
                    self._record_error(exc)
                    self._complete_unhandled_cycle()

                self._wait_for_command_cycle()

        except Exception as exc:
            self._record_error(exc)

            if not self.session.is_state(VoiceState.ERROR):
                self.session.fail(exc)

        finally:
            self._complete_listening_on_exit()

            with self._lock:
                self._active = False
                self._thread = None

    def _wait_while_paused(self) -> bool:
        while self.is_active and self._pause_event.is_set():
            if self._stop_event.wait(self.idle_wait):
                return True

        return not self.is_active

    def _wait_for_command_cycle(self) -> None:
        while self.is_active:
            if self.session.is_state(VoiceState.IDLE):
                return

            if self._stop_event.wait(self.idle_wait):
                return

    def _complete_unhandled_cycle(self) -> None:
        if self.session.is_state(VoiceState.PROCESSING):
            self.session.complete()

    def _complete_listening_on_exit(self) -> None:
        if self.session.is_state(VoiceState.LISTENING):
            self.session.complete()

    def _record_command(self, command: str) -> None:
        with self._lock:
            self._command_count += 1
            self._last_command = command

    def _record_error(self, error: Exception) -> None:
        message = str(error).strip() or type(error).__name__

        with self._lock:
            self._last_error = message
