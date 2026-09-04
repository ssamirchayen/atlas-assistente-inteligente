from pathlib import Path

from atlas.core import config


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_profile_configuration_is_safe_by_default() -> None:
    assert config.ATLAS_RUNTIME_PROFILE in {"auto", "lite", "standard", "full"}


def test_kernel_resolves_profile_before_heavy_components() -> None:
    source = (ROOT / "atlas" / "core" / "kernel.py").read_text(encoding="utf-8")
    profile_position = source.index("self.runtime_profile = RuntimeProfileService(")
    voice_position = source.index("self.voice_session = VoiceSession()")
    memory_position = source.index("self.memory = MemoryStore()")
    brain_position = source.index("self._brain_component = LazyComponent(")

    assert profile_position < voice_position < memory_position < brain_position


def test_profile_stage_does_not_change_feature_flags() -> None:
    source = (ROOT / "atlas" / "core" / "runtime_profile.py").read_text(
        encoding="utf-8"
    )

    assert "os.environ" not in source
    assert "subprocess" not in source
    assert "Popen" not in source
    assert "process_iter" not in source
