"""Sequências estruturadas e verificadas do Atlas Vision Etapa 10.

Uma sequência só é aceita quando contém de duas a três ações explícitas de
interface. Cada passo continua passando pelo pipeline normal do Atlas e a
execução para imediatamente se um passo falhar ou ficar inconclusivo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from atlas.vision.action_intent import extract_click_target
from atlas.vision.text_input_intent import extract_structured_text_input
from atlas.vision.uia_action_intent import extract_windows_uia_action


@dataclass(frozen=True, slots=True)
class StructuredInteractionSequence:
    steps: tuple[str, ...]


_SEQUENCE_SPLIT = re.compile(
    r"\s+(?:e\s+depois|e\s+em\s+seguida|depois|em\s+seguida)\s+",
    flags=re.IGNORECASE,
)

_BLOCKED_SEQUENCE_TERMS = {
    "apagar",
    "autorizar",
    "comprar",
    "confirmar",
    "deletar",
    "desinstalar",
    "enviar",
    "excluir",
    "finalizar",
    "instalar",
    "pagar",
    "pix",
    "publicar",
    "salvar",
    "senha",
    "transferir",
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(
        char for char in value if not unicodedata.combining(char)
    )
    return " ".join(value.split())


def has_sequence_connector(command: str) -> bool:
    return _SEQUENCE_SPLIT.search(command) is not None


def _is_blocked(step: str) -> bool:
    words = set(_normalize(step).split())
    return bool(words & _BLOCKED_SEQUENCE_TERMS)


def _is_structured_step(step: str) -> bool:
    return bool(
        extract_structured_text_input(step)
        or extract_windows_uia_action(step)
        or extract_click_target(step)
    )


def is_structured_sequence_attempt(command: str) -> bool:
    """Indica cadeia de UI parcialmente reconhecida que não deve cair no Planner."""

    if not has_sequence_connector(command):
        return False

    parts = tuple(
        part.strip()
        for part in _SEQUENCE_SPLIT.split(command)
        if part.strip()
    )
    return any(_is_structured_step(part) for part in parts)


def extract_structured_sequence(
    command: str,
) -> StructuredInteractionSequence | None:
    """Extrai até três passos não destrutivos e estruturalmente reconhecidos."""

    if not has_sequence_connector(command):
        return None

    steps = tuple(
        part.strip().rstrip(" .!?;:").strip()
        for part in _SEQUENCE_SPLIT.split(command)
        if part.strip()
    )

    if not 2 <= len(steps) <= 3:
        return None

    if any(_is_blocked(step) for step in steps):
        return None

    if not all(_is_structured_step(step) for step in steps):
        return None

    return StructuredInteractionSequence(steps=steps)
