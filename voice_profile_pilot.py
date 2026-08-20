"""Exibe o perfil de voz ativo sem abrir o microfone."""

from __future__ import annotations

from atlas.core.config import VOICE_PROFILE
from atlas.voice.profile import resolve_voice_profile


def main() -> None:
    profile = resolve_voice_profile(VOICE_PROFILE)
    print(f"Perfil de voz ativo: {profile.name}")
    print(f"Pausa final: {profile.pause_threshold:.2f}s")
    print(f"Calibração inicial: {profile.calibration_duration:.2f}s")
    print(f"Timeout de comando: {profile.command_timeout:.2f}s")
    print(
        "Limite da frase: "
        f"{profile.command_phrase_time_limit:.2f}s"
    )


if __name__ == "__main__":
    main()
