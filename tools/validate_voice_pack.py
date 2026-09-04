from __future__ import annotations

from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    required = [
        root / "atlas/voice/__init__.py",
        root / "atlas/voice/command_normalizer.py",
        root / "atlas/voice/continuous.py",
        root / "atlas/voice/interruption.py",
        root / "atlas/voice/latency.py",
        root / "atlas/voice/pipeline.py",
        root / "atlas/voice/playback.py",
        root / "atlas/voice/profile.py",
        root / "atlas/voice/response.py",
        root / "atlas/voice/session.py",
        root / "atlas/voice/speech.py",
        root / "atlas/voice/tts.py",
        root / "atlas/voice/tts_cache.py",
        root / "requirements-voice.txt",
    ]
    missing = [
        str(path.relative_to(root))
        for path in required
        if not path.is_file()
    ]
    if missing:
        print("Voice Pack incompleto:", ", ".join(missing))
        return 2

    spec_path = root / "packaging/atlas.spec"
    if not spec_path.is_file():
        print("packaging/atlas.spec não encontrado.")
        return 3

    spec = spec_path.read_text(encoding="utf-8")
    for token in (
        "collect_all(\"edge_tts\")",
        "atlas.voice.continuous",
        "atlas.voice.interruption",
        "atlas.voice.pipeline",
    ):
        if token not in spec:
            print(f"Spec sem dependência obrigatória: {token}")
            return 3

    try:
        import edge_tts

        from atlas.voice.continuous import ContinuousVoiceListener
        from atlas.voice.interruption import VoiceInterruptionMonitor
        from atlas.voice.playback import WindowsMciPlayer
        from atlas.voice.profile import resolve_voice_profile
        from atlas.voice.session import VoiceSession
        from atlas.voice.speech import SpeechInterface
        from atlas.voice.tts import EdgeTTSProvider
    except (ImportError, ModuleNotFoundError) as exc:
        print(f"Falha ao importar Voice Pack: {exc}")
        return 4

    profile = resolve_voice_profile("fast")
    provider = EdgeTTSProvider()

    checks = {
        "edge_tts": edge_tts is not None,
        "antonio": provider.voice == "pt-BR-AntonioNeural",
        "continuous": callable(ContinuousVoiceListener),
        "interruption": callable(VoiceInterruptionMonitor),
        "session": callable(VoiceSession),
        "player": callable(getattr(WindowsMciPlayer, "play", None)),
        "player_stop": callable(getattr(WindowsMciPlayer, "stop", None)),
        "direct_synthesis": callable(getattr(provider, "synthesize", None)),
        "profile": profile.name == "fast",
        "runtime": SpeechInterface.runtime_self_test(),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print("Voice Pack falhou em:", ", ".join(failed))
        return 5

    print(f"Voice Pack OK: edge / {provider.voice} / perfil {profile.name}")
    print("Modo EXE: síntese Python direta + playback MCI direto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
