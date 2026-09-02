"""Formulários estruturados e contextuais do Atlas Vision Etapa 11.

A Etapa 11 aceita apenas preenchimentos explícitos de dois a cinco campos.
Cada campo precisa ter nome e valor informados pelo usuário. Campos sensíveis
(senha, PIN, token, cartão etc.) são bloqueados antes de qualquer ação.

O executor mantém todos os campos vinculados ao mesmo contexto estrutural
(página DOM ou janela UIA) e nunca envia/submete o formulário automaticamente.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from atlas.vision.text_input_intent import StructuredTextInputRequest


@dataclass(frozen=True, slots=True)
class StructuredFormRequest:
    fields: tuple[StructuredTextInputRequest, ...]


_FORM_PREFIX = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?:preencha|preencher|complete|completar)\s+"
    r"(?:(?:o|a)\s+)?(?:formul[aá]rio|form)\b[:\s,-]*",
    flags=re.IGNORECASE,
)

_PAIR_SEPARATOR = re.compile(
    r"\s*(?:,|;)\s*|"
    r"\s+e\s+(?=(?:(?:o|a|no|na)\s+)?(?:campo|barra|caixa|editor)\s+)",
    flags=re.IGNORECASE,
)

_SINGLE_PAIR = re.compile(
    r"^\s*(?:(?:o|a|no|na)\s+)?"
    r"(?:(?P<marker>campo|barra|caixa|editor)\s+)?"
    r"(?P<target>.+?)\s+com\s+(?P<text>.+?)\s*$",
    flags=re.IGNORECASE,
)

_EXPLICIT_MULTI_FIELD_HINT = re.compile(
    r"(?:campo|barra|caixa|editor)\s+.+?\s+com\s+.+?"
    r"(?:,|;|\s+e\s+)\s*"
    r"(?:(?:o|a|no|na)\s+)?(?:campo|barra|caixa|editor)\s+.+?\s+com\s+",
    flags=re.IGNORECASE,
)

_SENSITIVE_TARGET_TERMS = {
    "cartao",
    "card",
    "codigo de seguranca",
    "cvv",
    "cvc",
    "pin",
    "password",
    "senha",
    "secret",
    "segredo",
    "token",
    "chave privada",
    "private key",
}

_MAX_FORM_FIELDS = 5


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _clean_target(value: str) -> str:
    return value.strip().strip('"“”\'').rstrip(" .!?;:").strip()


def _clean_text(value: str) -> str:
    return value.strip().strip('"“”\'').strip()


def _is_sensitive_target(target: str) -> bool:
    normalized = _normalize(target)
    return any(term in normalized for term in _SENSITIVE_TARGET_TERMS)


def _parse_colon_pairs(body: str) -> tuple[StructuredTextInputRequest, ...]:
    pieces = [piece.strip() for piece in re.split(r"\s*[;,]\s*", body) if piece.strip()]
    if len(pieces) < 2:
        return ()

    fields: list[StructuredTextInputRequest] = []
    for piece in pieces:
        if ":" not in piece:
            return ()
        target_raw, text_raw = piece.split(":", 1)
        target = _clean_target(target_raw)
        text = _clean_text(text_raw)
        if not target or not text:
            return ()
        fields.append(StructuredTextInputRequest(target=f"campo {target}", text=text))
    return tuple(fields)


def _parse_with_pairs(body: str) -> tuple[StructuredTextInputRequest, ...]:
    pieces = [piece.strip() for piece in _PAIR_SEPARATOR.split(body) if piece.strip()]
    if len(pieces) < 2:
        return ()

    fields: list[StructuredTextInputRequest] = []
    for piece in pieces:
        match = _SINGLE_PAIR.match(piece)
        if match is None:
            return ()
        marker = (match.group("marker") or "campo").strip()
        target_name = _clean_target(match.group("target"))
        text = _clean_text(match.group("text"))
        if not target_name or not text:
            return ()
        fields.append(
            StructuredTextInputRequest(
                target=f"{marker} {target_name}".strip(),
                text=text,
            )
        )
    return tuple(fields)


def is_structured_form_attempt(command: str) -> bool:
    raw = command.strip()
    if not raw:
        return False
    if _FORM_PREFIX.match(raw):
        return True
    return _EXPLICIT_MULTI_FIELD_HINT.search(raw) is not None


def extract_structured_form(command: str) -> StructuredFormRequest | None:
    """Extrai dois a cinco pares campo/valor explicitamente informados."""

    raw = command.strip()
    if not raw:
        return None

    prefix = _FORM_PREFIX.match(raw)
    if prefix is not None:
        body = raw[prefix.end():].strip()
        if body.casefold().startswith("com "):
            body = body[4:].strip()
    else:
        if not _EXPLICIT_MULTI_FIELD_HINT.search(raw):
            return None
        # Aceita a forma falada: "preencha o campo X com A e o campo Y com B".
        body = re.sub(
            r"^\s*(?:por\s+favor\s+)?(?:preencha|preencher|complete|completar)\s+",
            "",
            raw,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

    fields = _parse_colon_pairs(body) or _parse_with_pairs(body)
    if not 2 <= len(fields) <= _MAX_FORM_FIELDS:
        return None

    if any(_is_sensitive_target(field.target) for field in fields):
        return None

    normalized_targets = [_normalize(field.target) for field in fields]
    if len(set(normalized_targets)) != len(normalized_targets):
        return None

    return StructuredFormRequest(fields=fields)
