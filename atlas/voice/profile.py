"""Perfis declarativos de desempenho para o pipeline de voz."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoicePerformanceProfile:
    """Parâmetros de voz agrupados sem alterar a API de reconhecimento."""

    name: str
    pause_threshold: float
    non_speaking_duration: float
    phrase_threshold: float
    calibration_duration: float
    command_timeout: float
    command_phrase_time_limit: float
    continuous_listen_timeout: float
    continuous_phrase_time_limit: float
    continuous_idle_wait: float

    def __post_init__(self) -> None:
        values = (
            self.pause_threshold,
            self.non_speaking_duration,
            self.phrase_threshold,
            self.calibration_duration,
            self.command_timeout,
            self.command_phrase_time_limit,
            self.continuous_listen_timeout,
            self.continuous_phrase_time_limit,
            self.continuous_idle_wait,
        )

        if not self.name.strip():
            raise ValueError("O nome do perfil de voz é obrigatório.")
        if any(value <= 0 for value in values):
            raise ValueError("Os tempos do perfil de voz devem ser positivos.")
        if self.non_speaking_duration > self.pause_threshold:
            raise ValueError(
                "A duração sem fala não pode superar a pausa final."
            )


BALANCED_VOICE_PROFILE = VoicePerformanceProfile(
    name="balanced",
    pause_threshold=1.7,
    non_speaking_duration=1.0,
    phrase_threshold=0.2,
    calibration_duration=1.0,
    command_timeout=10.0,
    command_phrase_time_limit=20.0,
    continuous_listen_timeout=2.0,
    continuous_phrase_time_limit=15.0,
    continuous_idle_wait=0.1,
)

FAST_VOICE_PROFILE = VoicePerformanceProfile(
    name="fast",
    pause_threshold=0.9,
    non_speaking_duration=0.45,
    phrase_threshold=0.15,
    calibration_duration=0.5,
    command_timeout=6.0,
    command_phrase_time_limit=12.0,
    continuous_listen_timeout=1.25,
    continuous_phrase_time_limit=10.0,
    continuous_idle_wait=0.05,
)

ACCURATE_VOICE_PROFILE = VoicePerformanceProfile(
    name="accurate",
    pause_threshold=2.0,
    non_speaking_duration=1.2,
    phrase_threshold=0.25,
    calibration_duration=1.5,
    command_timeout=12.0,
    command_phrase_time_limit=25.0,
    continuous_listen_timeout=2.5,
    continuous_phrase_time_limit=20.0,
    continuous_idle_wait=0.15,
)

_VOICE_PROFILES = {
    profile.name: profile
    for profile in (
        BALANCED_VOICE_PROFILE,
        FAST_VOICE_PROFILE,
        ACCURATE_VOICE_PROFILE,
    )
}


def resolve_voice_profile(
    value: str | VoicePerformanceProfile | None,
) -> VoicePerformanceProfile:
    """Resolve um perfil; configuração desconhecida usa o modo equilibrado."""

    if isinstance(value, VoicePerformanceProfile):
        return value

    normalized = str(value or "balanced").strip().casefold()
    return _VOICE_PROFILES.get(normalized, BALANCED_VOICE_PROFILE)
