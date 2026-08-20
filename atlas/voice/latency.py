"""Telemetria local e sem conteúdo para ciclos de voz."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from statistics import fmean
from threading import RLock
from time import monotonic
from typing import Any

from atlas.voice.session import VoiceSession, VoiceSnapshot, VoiceState


class VoiceCycleOutcome(StrEnum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class VoiceLatencyRecord:
    """Tempos de um ciclo sem transcrição ou conteúdo da resposta."""

    sequence: int
    started_at: datetime
    finished_at: datetime
    outcome: VoiceCycleOutcome
    recognized: bool
    listening_ms: float
    processing_ms: float
    speaking_ms: float
    total_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "outcome": self.outcome.value,
            "recognized": self.recognized,
            "listening_ms": self.listening_ms,
            "processing_ms": self.processing_ms,
            "speaking_ms": self.speaking_ms,
            "total_ms": self.total_ms,
        }


@dataclass(slots=True)
class _ActiveVoiceCycle:
    sequence: int
    started_at: datetime
    started_tick: float
    phase: VoiceState
    phase_tick: float
    recognized: bool = False
    listening_ms: float = 0.0
    processing_ms: float = 0.0
    speaking_ms: float = 0.0


class VoiceLatencyTracker:
    """Observa uma `VoiceSession` e mantém um histórico limitado em memória."""

    def __init__(
        self,
        session: VoiceSession,
        *,
        history_limit: int = 50,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if history_limit <= 0:
            raise ValueError("O histórico de latência deve ser positivo.")
        if not callable(clock):
            raise TypeError("O relógio de latência deve ser chamável.")

        self._session = session
        self._clock = clock
        self._lock = RLock()
        self._records: deque[VoiceLatencyRecord] = deque(
            maxlen=history_limit
        )
        self._active: _ActiveVoiceCycle | None = None
        self._cycle_sequence = 0
        self._closed = False
        session.subscribe(self._observe)

    def latest(self) -> VoiceLatencyRecord | None:
        with self._lock:
            return self._records[-1] if self._records else None

    def history(self) -> tuple[VoiceLatencyRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def summary(self) -> dict[str, float | int | None]:
        with self._lock:
            records = tuple(self._records)

        if not records:
            return {
                "cycles": 0,
                "completed": 0,
                "interrupted": 0,
                "errors": 0,
                "average_total_ms": None,
                "maximum_total_ms": None,
            }

        return {
            "cycles": len(records),
            "completed": sum(
                record.outcome is VoiceCycleOutcome.COMPLETED
                for record in records
            ),
            "interrupted": sum(
                record.outcome is VoiceCycleOutcome.INTERRUPTED
                for record in records
            ),
            "errors": sum(
                record.outcome is VoiceCycleOutcome.ERROR
                for record in records
            ),
            "average_total_ms": round(
                fmean(record.total_ms for record in records),
                2,
            ),
            "maximum_total_ms": max(
                record.total_ms for record in records
            ),
        }

    def close(self) -> bool:
        with self._lock:
            if self._closed:
                return False
            self._closed = True
            self._active = None

        self._session.unsubscribe(self._observe)
        return True

    def _observe(self, snapshot: VoiceSnapshot) -> None:
        tick = self._clock()

        with self._lock:
            if self._closed:
                return

            if snapshot.state is VoiceState.LISTENING:
                self._cycle_sequence += 1
                self._active = _ActiveVoiceCycle(
                    sequence=self._cycle_sequence,
                    started_at=snapshot.changed_at,
                    started_tick=tick,
                    phase=VoiceState.LISTENING,
                    phase_tick=tick,
                )
                return

            active = self._active

            if active is None:
                return

            self._finish_phase(active, tick)
            active.recognized = active.recognized or bool(
                snapshot.last_transcript
            )

            if snapshot.state in {
                VoiceState.PROCESSING,
                VoiceState.SPEAKING,
            }:
                active.phase = snapshot.state
                active.phase_tick = tick
                return

            outcomes = {
                VoiceState.IDLE: VoiceCycleOutcome.COMPLETED,
                VoiceState.INTERRUPTED: VoiceCycleOutcome.INTERRUPTED,
                VoiceState.ERROR: VoiceCycleOutcome.ERROR,
            }
            outcome = outcomes.get(snapshot.state)

            if outcome is None:
                return

            self._records.append(
                VoiceLatencyRecord(
                    sequence=active.sequence,
                    started_at=active.started_at,
                    finished_at=snapshot.changed_at,
                    outcome=outcome,
                    recognized=active.recognized,
                    listening_ms=round(active.listening_ms, 2),
                    processing_ms=round(active.processing_ms, 2),
                    speaking_ms=round(active.speaking_ms, 2),
                    total_ms=round(
                        max(0.0, tick - active.started_tick) * 1000,
                        2,
                    ),
                )
            )
            self._active = None

    @staticmethod
    def _finish_phase(active: _ActiveVoiceCycle, tick: float) -> None:
        elapsed_ms = max(0.0, tick - active.phase_tick) * 1000

        if active.phase is VoiceState.LISTENING:
            active.listening_ms += elapsed_ms
        elif active.phase is VoiceState.PROCESSING:
            active.processing_ms += elapsed_ms
        elif active.phase is VoiceState.SPEAKING:
            active.speaking_ms += elapsed_ms
