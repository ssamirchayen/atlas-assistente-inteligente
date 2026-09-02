"""Intenção explícita de preenchimento estrutural de campos.

A Etapa 10 só captura comandos que indicam claramente o texto e o campo alvo.
O conteúdo nunca é enviado para campos de senha e não existe fallback para
teclado físico, coordenadas ou Vision quando o controle não pode ser validado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StructuredTextInputRequest:
    target: str
    text: str


_FILL_FIELD_WITH = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?:preencha|preencher|preenche)\s+"
    r"(?:(?:o|a|no|na)\s+)?"
    r"(?P<target>.+?)\s+com\s+(?P<text>.+?)\s*$",
    flags=re.IGNORECASE,
)

_TYPE_IN_FIELD = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?:digite|digitar|escreva|escrever)\s+"
    r"(?P<text>.+?)\s+"
    r"(?:no|na|em)\s+"
    r"(?P<target>.+?)\s*$",
    flags=re.IGNORECASE,
)


_FIELD_MARKERS = (
    "campo",
    "barra",
    "caixa",
    "editor",
    "pesquisa",
    "busca",
    "texto",
    "input",
)


def _clean_target(value: str) -> str:
    return value.strip().strip('"“”\'').rstrip(" .!?;:").strip()


def _clean_text(value: str) -> str:
    return value.strip().strip('"“”\'').strip()


def _looks_like_field(target: str) -> bool:
    normalized = target.casefold()
    return any(marker in normalized for marker in _FIELD_MARKERS)


def extract_structured_text_input(
    command: str,
) -> StructuredTextInputRequest | None:
    """Extrai texto + campo quando ambos são explicitamente informados."""

    raw = command.strip()
    if not raw:
        return None

    for pattern in (_FILL_FIELD_WITH, _TYPE_IN_FIELD):
        match = pattern.match(raw)
        if match is None:
            continue

        target = _clean_target(match.group("target"))
        text = _clean_text(match.group("text"))

        if not target or not text or not _looks_like_field(target):
            return None

        return StructuredTextInputRequest(target=target, text=text)

    return None
