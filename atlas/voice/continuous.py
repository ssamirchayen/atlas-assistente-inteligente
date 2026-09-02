from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, RLock, Thread, current_thread

from atlas.core.config import ATLAS_NAME
from atlas.utils.text import remove_wake_word
from atlas.voice.command_normalizer import normalize_voice_command
from atlas.voice.session import VoiceState
from atlas.voice.speech import SpeechInterface


@dataclass(frozen=True, slots=True)
class ContinuousEndpointingPolicy:
    """Regras de término de frase para a escuta contínua.

    O reconhecimento contínuo precisa tolerar pausas naturais sem herdar o
    endpoint agressivo do perfil ``fast``. Esses limites são locais à captura
    contínua e são restaurados imediatamente após cada frase.
    """

    pause_threshold: float = 2.4
    non_speaking_duration: float = 0.8
    minimum_phrase_time_limit: float = 20.0

    def __post_init__(self) -> None:
        if self.pause_threshold <= 0:
            raise ValueError("A pausa contínua deve ser positiva.")
        if self.non_speaking_duration <= 0:
            raise ValueError("A duração sem fala deve ser positiva.")
        if self.non_speaking_duration > self.pause_threshold:
            raise ValueError(
                "A duração sem fala não pode superar a pausa contínua."
            )
        if self.minimum_phrase_time_limit <= 0:
            raise ValueError("O limite mínimo da frase deve ser positivo.")


DEFAULT_CONTINUOUS_ENDPOINTING = ContinuousEndpointingPolicy()


@dataclass(frozen=True, slots=True)
class _RecognizerEndpointSnapshot:
    pause_threshold: float | None
    non_speaking_duration: float | None


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
        endpointing_policy: ContinuousEndpointingPolicy | None = None,
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
        self.endpointing_policy = (
            endpointing_policy or DEFAULT_CONTINUOUS_ENDPOINTING
        )

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

                endpoint_snapshot = self._apply_continuous_endpointing()

                try:
                    transcript = self.speech.listen(
                        prompt="",
                        retry_on_failure=False,
                        timeout=self.listen_timeout,
                        phrase_time_limit=self._effective_phrase_time_limit(),
                        verbose=False,
                    )
                finally:
                    self._restore_continuous_endpointing(endpoint_snapshot)

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

                command = normalize_voice_command(command)

                if not command:
                    # Autocorreção explícita ou fala sem comando seguro.
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

    def _effective_phrase_time_limit(self) -> float:
        """Evita cortar comandos longos por um limite do perfil rápido."""

        return max(
            self.phrase_time_limit,
            self.endpointing_policy.minimum_phrase_time_limit,
        )

    def _apply_continuous_endpointing(self) -> _RecognizerEndpointSnapshot:
        """Aplica endpointing robusto somente durante a captura contínua.

        O perfil ``fast`` continua rápido para o restante do Atlas, mas a
        escuta contínua ganha margem suficiente para pausas naturais no meio
        de comandos como ``digite ... na barra de pesquisa``.
        """

        recognizer = getattr(self.speech, "recognizer", None)
        if recognizer is None:
            return _RecognizerEndpointSnapshot(None, None)

        pause_value = getattr(recognizer, "pause_threshold", None)
        non_speaking_value = getattr(
            recognizer,
            "non_speaking_duration",
            None,
        )

        pause_previous = (
            float(pause_value)
            if isinstance(pause_value, (int, float))
            else None
        )
        non_speaking_previous = (
            float(non_speaking_value)
            if isinstance(non_speaking_value, (int, float))
            else None
        )

        if pause_previous is not None:
            recognizer.pause_threshold = max(
                pause_previous,
                self.endpointing_policy.pause_threshold,
            )

        if non_speaking_previous is not None:
            recognizer.non_speaking_duration = max(
                non_speaking_previous,
                self.endpointing_policy.non_speaking_duration,
            )

        return _RecognizerEndpointSnapshot(
            pause_previous,
            non_speaking_previous,
        )

    def _restore_continuous_endpointing(
        self,
        snapshot: _RecognizerEndpointSnapshot,
    ) -> None:
        recognizer = getattr(self.speech, "recognizer", None)
        if recognizer is None:
            return

        if snapshot.pause_threshold is not None:
            recognizer.pause_threshold = snapshot.pause_threshold

        if snapshot.non_speaking_duration is not None:
            recognizer.non_speaking_duration = (
                snapshot.non_speaking_duration
            )

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
