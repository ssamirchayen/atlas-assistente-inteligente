from __future__ import annotations

import pytest

from atlas.voice.response import normalize_spoken_text, split_for_speech


def test_normalize_spoken_text_compacts_whitespace() -> None:
    assert normalize_spoken_text(" Olá,   mundo!\nTudo bem? ") == (
        "Olá, mundo! Tudo bem?"
    )


def test_short_response_stays_in_one_chunk() -> None:
    assert split_for_speech("Resposta curta.", max_chars=100) == (
        "Resposta curta.",
    )


def test_long_response_is_split_on_natural_boundaries() -> None:
    message = (
        "Primeira frase com algum conteúdo. "
        "Segunda frase também tem conteúdo. "
        "Terceira frase encerra a resposta."
    )

    chunks = split_for_speech(message, max_chars=80)

    assert len(chunks) >= 2
    assert " ".join(chunks) == message
    assert all(len(chunk) <= 80 for chunk in chunks)


def test_long_single_sentence_falls_back_to_word_boundaries() -> None:
    message = " ".join(["palavra"] * 40)

    chunks = split_for_speech(message, max_chars=80)

    assert len(chunks) > 1
    assert " ".join(chunks) == message
    assert all(len(chunk) <= 80 for chunk in chunks)


def test_chunk_limit_rejects_too_small_value() -> None:
    with pytest.raises(ValueError, match="80"):
        split_for_speech("texto", max_chars=79)
