from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import Condition, Event, RLock
from typing import Any


class VoiceState(str, Enum):
    """Estados possíveis do ciclo de voz do Atlas."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


class VoiceTransitionError(RuntimeError):
    """Indica uma tentativa inválida de transição do estado de voz."""

    def __init__(
        self,
        current_state: VoiceState,
        requested_state: VoiceState,
    ) -> None:
        self.current_state = current_state
        self.requested_state = requested_state
        super().__init__(
            "Transição de voz inválida: "
            f"{current_state.value} -> {requested_state.value}."
        )


@dataclass(frozen=True, slots=True)
class VoiceSnapshot:
    """Representação imutável do estado atual da sessão de voz."""

    state: VoiceState
    previous_state: VoiceState | None
    changed_at: datetime
    sequence: int
    last_transcript: str | None
    interruption_reason: str | None
    error_message: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "previous_state": (
                self.previous_state.value
                if self.previous_state is not None
                else None
            ),
            "changed_at": self.changed_at.isoformat(),
            "sequence": self.sequence,
            "last_transcript": self.last_transcript,
            "interruption_reason": self.interruption_reason,
            "error_message": self.error_message,
        }


VoiceListener = Callable[[VoiceSnapshot], None]


class VoiceSession:
    """
    Centraliza o ciclo de voz do Atlas de forma segura entre threads.

    A sessão é a fonte única de verdade para microfone, processamento,
    síntese de fala e interrupções. Cada mudança produz um snapshot
    imutável e pode ser observada pela interface gráfica.
    """

    _ALLOWED_TRANSITIONS: dict[VoiceState, set[VoiceState]] = {
        VoiceState.IDLE: {
            VoiceState.LISTENING,
            VoiceState.PROCESSING,
            VoiceState.SPEAKING,
            VoiceState.INTERRUPTED,
            VoiceState.ERROR,
        },
        VoiceState.LISTENING: {
            VoiceState.IDLE,
            VoiceState.PROCESSING,
            VoiceState.INTERRUPTED,
            VoiceState.ERROR,
        },
        VoiceState.PROCESSING: {
            VoiceState.IDLE,
            VoiceState.LISTENING,
            VoiceState.SPEAKING,
            VoiceState.INTERRUPTED,
            VoiceState.ERROR,
        },
        VoiceState.SPEAKING: {
            VoiceState.IDLE,
            VoiceState.LISTENING,
            VoiceState.INTERRUPTED,
            VoiceState.ERROR,
        },
        VoiceState.INTERRUPTED: {
            VoiceState.IDLE,
            VoiceState.LISTENING,
            VoiceState.ERROR,
        },
        VoiceState.ERROR: {
            VoiceState.IDLE,
            VoiceState.LISTENING,
            VoiceState.SPEAKING,
        },
    }

    def __init__(self) -> None:
        self._lock = RLock()
        self._condition = Condition(self._lock)
        self._interruption_event = Event()
        self._state = VoiceState.IDLE
        self._previous_state: VoiceState | None = None
        self._changed_at = datetime.now(timezone.utc)
        self._sequence = 0
        self._last_transcript: str | None = None
        self._interruption_reason: str | None = None
        self._error_message: str | None = None
        self._listeners: list[VoiceListener] = []

    @property
    def state(self) -> VoiceState:
        return self.snapshot().state

    def is_state(self, state: VoiceState) -> bool:
        return self.state is state

    def start_listening(self) -> VoiceSnapshot:
        """Inicia um novo ciclo e limpa interrupções anteriores."""

        return self.transition(
            VoiceState.LISTENING,
            clear_cycle=True,
        )

    def start_processing(
        self,
        transcript: str | None = None,
    ) -> VoiceSnapshot:
        """Marca que a fala reconhecida está sendo processada."""

        return self.transition(
            VoiceState.PROCESSING,
            transcript=transcript,
        )

    def start_speaking(self) -> VoiceSnapshot:
        """Marca o início da síntese de voz do Atlas."""

        return self.transition(VoiceState.SPEAKING)

    def complete(self) -> VoiceSnapshot:
        """Finaliza o ciclo atual e retorna ao estado ocioso."""

        return self.transition(VoiceState.IDLE)

    def interrupt(self, reason: str | None = None) -> bool:
        """
        Solicita a interrupção cooperativa do ciclo de voz.

        A primeira solicitação retorna ``True``. Solicitações repetidas
        enquanto a sessão já está interrompida retornam ``False``.
        """

        normalized_reason = self._normalize_optional_text(reason)

        listeners: tuple[VoiceListener, ...]

        with self._condition:
            if self._state is VoiceState.INTERRUPTED:
                return False

            if (
                VoiceState.INTERRUPTED
                not in self._ALLOWED_TRANSITIONS[self._state]
            ):
                raise VoiceTransitionError(
                    self._state,
                    VoiceState.INTERRUPTED,
                )

            self._previous_state = self._state
            self._state = VoiceState.INTERRUPTED
            self._changed_at = datetime.now(timezone.utc)
            self._sequence += 1
            self._interruption_reason = normalized_reason
            self._interruption_event.set()
            snapshot = self._snapshot_unlocked()
            listeners = tuple(self._listeners)
            self._condition.notify_all()

        self._notify_listeners(listeners, snapshot)
        return True

    def fail(self, error: str | Exception) -> VoiceSnapshot:
        """Registra uma falha no ciclo de voz."""

        message = str(error).strip() or type(error).__name__
        return self.transition(
            VoiceState.ERROR,
            error_message=message,
        )

    def reset(self) -> VoiceSnapshot:
        """Limpa metadados e restaura a sessão para um novo ciclo."""

        with self._lock:
            current_state = self._state

        if current_state is not VoiceState.IDLE:
            self.transition(VoiceState.IDLE)

        return self._clear_cycle_metadata()

    def transition(
        self,
        state: VoiceState,
        *,
        transcript: str | None = None,
        interruption_reason: str | None = None,
        error_message: str | None = None,
        clear_cycle: bool = False,
    ) -> VoiceSnapshot:
        """Realiza uma transição validada e notifica os observadores."""

        requested_state = VoiceState(state)
        listeners: tuple[VoiceListener, ...]

        with self._condition:
            if requested_state is self._state:
                return self._snapshot_unlocked()

            allowed_states = self._ALLOWED_TRANSITIONS[self._state]

            if requested_state not in allowed_states:
                raise VoiceTransitionError(
                    self._state,
                    requested_state,
                )

            if clear_cycle:
                self._last_transcript = None
                self._interruption_reason = None
                self._error_message = None
                self._interruption_event.clear()

            normalized_transcript = self._normalize_optional_text(
                transcript
            )
            normalized_reason = self._normalize_optional_text(
                interruption_reason
            )
            normalized_error = self._normalize_optional_text(
                error_message
            )

            self._previous_state = self._state
            self._state = requested_state
            self._changed_at = datetime.now(timezone.utc)
            self._sequence += 1

            if normalized_transcript is not None:
                self._last_transcript = normalized_transcript

            if requested_state is VoiceState.INTERRUPTED:
                self._interruption_reason = normalized_reason
                self._interruption_event.set()

            if requested_state is VoiceState.ERROR:
                self._error_message = normalized_error

            snapshot = self._snapshot_unlocked()
            listeners = tuple(self._listeners)
            self._condition.notify_all()

        self._notify_listeners(listeners, snapshot)
        return snapshot

    def interruption_requested(self) -> bool:
        """Informa se uma interrupção cooperativa está pendente."""

        return self._interruption_event.is_set()

    def wait_for_interruption(
        self,
        timeout: float | None = None,
    ) -> bool:
        if timeout is not None and timeout < 0:
            raise ValueError(
                "O tempo limite de espera não pode ser negativo."
            )

        return self._interruption_event.wait(timeout)

    def wait_for_state(
        self,
        state: VoiceState,
        timeout: float | None = None,
    ) -> bool:
        """Aguarda a sessão alcançar o estado solicitado."""

        if timeout is not None and timeout < 0:
            raise ValueError(
                "O tempo limite de espera não pode ser negativo."
            )

        requested_state = VoiceState(state)

        with self._condition:
            return self._condition.wait_for(
                lambda: self._state is requested_state,
                timeout=timeout,
            )

    def subscribe(self, listener: VoiceListener) -> None:
        """Registra um observador para mudanças futuras de estado."""

        if not callable(listener):
            raise TypeError("O observador da voz deve ser chamável.")

        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def unsubscribe(self, listener: VoiceListener) -> bool:
        """Remove um observador previamente registrado."""

        with self._lock:
            if listener not in self._listeners:
                return False

            self._listeners.remove(listener)
            return True

    def snapshot(self) -> VoiceSnapshot:
        """Retorna uma cópia consistente do estado atual."""

        with self._lock:
            return self._snapshot_unlocked()

    def _clear_cycle_metadata(self) -> VoiceSnapshot:
        listeners: tuple[VoiceListener, ...]

        with self._condition:
            changed = any(
                value is not None
                for value in (
                    self._last_transcript,
                    self._interruption_reason,
                    self._error_message,
                )
            ) or self._interruption_event.is_set()

            self._last_transcript = None
            self._interruption_reason = None
            self._error_message = None
            self._interruption_event.clear()

            if changed:
                self._changed_at = datetime.now(timezone.utc)
                self._sequence += 1

            snapshot = self._snapshot_unlocked()
            listeners = tuple(self._listeners) if changed else ()

            if changed:
                self._condition.notify_all()

        self._notify_listeners(listeners, snapshot)
        return snapshot

    def _snapshot_unlocked(self) -> VoiceSnapshot:
        return VoiceSnapshot(
            state=self._state,
            previous_state=self._previous_state,
            changed_at=self._changed_at,
            sequence=self._sequence,
            last_transcript=self._last_transcript,
            interruption_reason=self._interruption_reason,
            error_message=self._error_message,
        )

    @staticmethod
    def _notify_listeners(
        listeners: tuple[VoiceListener, ...],
        snapshot: VoiceSnapshot,
    ) -> None:
        for listener in listeners:
            try:
                listener(snapshot)
            except Exception:
                # Um observador visual não pode interromper o ciclo de voz.
                continue

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip()
        return normalized or None
