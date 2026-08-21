from __future__ import annotations

from pathlib import Path

import pytest

from atlas.voice.tts_cache import TTSFileCache


def test_cache_key_changes_with_voice_configuration() -> None:
    first = TTSFileCache.key_for(
        "Olá",
        voice="voice-a",
        rate="+0%",
        volume="+0%",
        pitch="+0Hz",
    )
    second = TTSFileCache.key_for(
        "Olá",
        voice="voice-b",
        rate="+0%",
        volume="+0%",
        pitch="+0Hz",
    )

    assert first != second
    assert len(first) == 64


def test_cache_store_and_get_never_expose_plain_text_in_filename(tmp_path: Path) -> None:
    cache = TTSFileCache(tmp_path / "voice", max_entries=4)
    source = tmp_path / "audio.mp3"
    source.write_bytes(b"fake mp3")
    secret = "resposta confidencial"
    key = cache.key_for(
        secret,
        voice="voice",
        rate="+0%",
        volume="+0%",
        pitch="+0Hz",
    )

    stored = cache.store(key, source)

    assert cache.get(key) == stored
    assert stored.read_bytes() == b"fake mp3"
    assert secret not in stored.name


def test_cache_trims_old_entries(tmp_path: Path) -> None:
    cache = TTSFileCache(tmp_path / "voice", max_entries=2)

    for index in range(3):
        source = tmp_path / f"{index}.mp3"
        source.write_bytes(str(index).encode())
        cache.store(f"{index:064d}", source)

    assert len(list(cache.directory.glob("*.mp3"))) == 2


def test_cache_rejects_empty_source(tmp_path: Path) -> None:
    cache = TTSFileCache(tmp_path / "voice")
    source = tmp_path / "empty.mp3"
    source.write_bytes(b"")

    with pytest.raises(ValueError, match="vazio"):
        cache.store("a" * 64, source)
