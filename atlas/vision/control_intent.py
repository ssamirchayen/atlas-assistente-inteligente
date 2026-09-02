"""Controles estruturais de estado do Atlas Vision Etapa 13.

Somente comandos explícitos para checkbox, radio ou switch são aceitos. O
parser não concede permissão para clicar em elementos genéricos e não aceita
ações finais como enviar, comprar, pagar ou excluir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StructuredControlRequest:
    target: str
    action: str

    @property
    def desired_state(self) -> bool:
        return self.action in {"check", "select"}


_CONTROL = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?P<verb>marque|marcar|desmarque|desmarcar|ative|ativar|"
    r"desative|desativar|selecione|selecionar)\s+"
    r"(?:(?:a|o)\s+)?"
    r"(?P<kind>caixa(?:\s+de\s+sele[cç][aã]o)?|checkbox|op[cç][aã]o|"
    r"radio|bot[aã]o\s+de\s+op[cç][aã]o|switch|interruptor)\s+"
    r"(?P<label>.+?)\s*$",
    flags=re.IGNORECASE,
)

_BLOCKED_TERMS = {
    "apagar",
    "comprar",
    "confirmar compra",
    "deletar",
    "enviar",
    "excluir",
    "finalizar",
    "pagar",
    "publicar",
    "salvar",
    "transferir",
}


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _clean(value: str) -> str:
    return value.strip().strip('"“”\'').rstrip(" .!?;:").strip()


def extract_structured_control(
    command: str,
) -> StructuredControlRequest | None:
    """Extrai uma alteração explícita de estado em controle estrutural."""

    match = _CONTROL.match(command.strip())
    if match is None:
        return None

    label = _clean(match.group("label"))
    kind = _clean(match.group("kind"))
    if not label:
        return None

    normalized_label = _normalize(label)
    if any(term in normalized_label for term in _BLOCKED_TERMS):
        return None

    verb = _normalize(match.group("verb"))
    normalized_kind = _normalize(kind)

    if verb in {"desmarque", "desmarcar", "desative", "desativar"}:
        action = "uncheck"
    elif normalized_kind in {
        "opcao",
        "radio",
        "botao de opcao",
    }:
        action = "select"
    else:
        action = "check"

    if action == "uncheck" and normalized_kind in {
        "opcao",
        "radio",
        "botao de opcao",
    }:
        return None

    return StructuredControlRequest(
        target=f"{kind} {label}".strip(),
        action=action,
    )

