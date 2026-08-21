"""Preparação de respostas para fala natural e de baixa latência."""

from __future__ import annotations

import re

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+")
_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s*")
_MARKDOWN_BULLET = re.compile(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+")
_MARKDOWN_EMPHASIS = re.compile(r"[*_~`]+")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RAW_URL = re.compile(r"https?://\S+")
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)


def normalize_spoken_text(message: str) -> str:
    """Converte uma resposta visual em texto adequado para TTS."""

    text = str(message)
    text = _CODE_FENCE.sub(" ", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _RAW_URL.sub(" link ", text)
    text = _MARKDOWN_HEADING.sub("", text)
    text = _MARKDOWN_BULLET.sub("", text)
    text = _MARKDOWN_EMPHASIS.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def split_for_speech(message: str, *, max_chars: int = 260) -> tuple[str, ...]:
    """Divide respostas em blocos naturais para antecipar o áudio."""

    if max_chars < 80:
        raise ValueError("O limite de fala deve ter pelo menos 80 caracteres.")

    text = normalize_spoken_text(message)
    if not text:
        return ()
    if len(text) <= max_chars:
        return (text,)

    sentences = [
        part.strip()
        for part in _SENTENCE_BOUNDARY.split(text)
        if part.strip()
    ]

    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        parts = (
            _split_long_fragment(sentence, max_chars=max_chars)
            if len(sentence) > max_chars
            else [sentence]
        )

        for part in parts:
            candidate = f"{current} {part}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = part
            else:
                current = candidate

    if current:
        chunks.append(current)

    return tuple(chunks)


def _split_long_fragment(fragment: str, *, max_chars: int) -> list[str]:
    clauses = [
        part.strip()
        for part in re.split(r"(?<=,)\s+", fragment)
        if part.strip()
    ]

    if len(clauses) > 1:
        chunks: list[str] = []
        current = ""

        for clause in clauses:
            candidate = f"{current} {clause}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = clause
            else:
                current = candidate

        if current:
            chunks.append(current)

        if all(len(item) <= max_chars for item in chunks):
            return chunks

    words = fragment.split()
    chunks = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def sentence_pause_seconds(chunk: str, *, base_ms: int = 90) -> float:
    """Pausa prosódica curta, ajustada pela pontuação final."""

    text = chunk.rstrip()
    if not text:
        return 0.0

    multiplier = 1.0

    if text.endswith("?"):
        multiplier = 1.15
    elif text.endswith("!"):
        multiplier = 1.05
    elif text.endswith((",", ";", ":")):
        multiplier = 0.55

    return max(0, base_ms) * multiplier / 1000.0
