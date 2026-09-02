"""Seleção estrutural de opções para o Atlas Vision Etapa 12.

A intenção aceita apenas comandos explícitos que informam tanto a opção quanto
um controle alvo (campo/lista/caixa seletora). A execução continua restrita a
controles estruturais; a camada visual nunca recebe permissão de selecionar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from atlas.vision.form_intent import StructuredFormRequest, extract_structured_form
from atlas.vision.text_input_intent import (
    StructuredTextInputRequest,
    extract_structured_text_input,
)


@dataclass(frozen=True, slots=True)
class StructuredOptionSelectionRequest:
    target: str
    option: str


@dataclass(frozen=True, slots=True)
class StructuredContextualFormRequest:
    fields: tuple[StructuredTextInputRequest, ...]
    selections: tuple[StructuredOptionSelectionRequest, ...]


_SELECT_OPTION = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?:selecione|selecionar|escolha|escolher)\s+"
    r"(?:(?:a|o)\s+op[cç][aã]o\s+)?"
    r"(?P<option>.+?)\s+"
    r"(?:no|na|em)\s+"
    r"(?P<target>.+?)\s*$",
    flags=re.IGNORECASE,
)

_SELECTION_START = re.compile(
    r"\s+(?:e\s+)?(?=(?:selecione|escolha)\b)",
    flags=re.IGNORECASE,
)

_SELECTION_SPLIT = re.compile(
    r"\s+e\s+(?=(?:selecione|escolha)\b)",
    flags=re.IGNORECASE,
)

_FILL_HINT = re.compile(
    r"\b(?:preencha|preencher|preenche|complete|completar|digite|escreva)\b",
    flags=re.IGNORECASE,
)

_SELECT_HINT = re.compile(
    r"\b(?:selecione|selecionar|escolha|escolher)\b",
    flags=re.IGNORECASE,
)

_TARGET_MARKERS = (
    "campo",
    "lista",
    "caixa",
    "menu",
    "seletor",
    "combobox",
    "combo",
    "select",
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

_MAX_CONTEXTUAL_OPERATIONS = 6
_MAX_SELECTIONS = 3


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _clean(value: str) -> str:
    return value.strip().strip('"“”\'').rstrip(" .!?;:").strip()


def _looks_like_select_target(target: str) -> bool:
    normalized = _normalize(target)
    return any(marker in normalized for marker in _TARGET_MARKERS)


def _is_sensitive_target(target: str) -> bool:
    normalized = _normalize(target)
    return any(term in normalized for term in _SENSITIVE_TARGET_TERMS)


def extract_structured_option_selection(
    command: str,
) -> StructuredOptionSelectionRequest | None:
    """Extrai opção + controle alvo de um comando de seleção explícito."""

    raw = command.strip()
    if not raw:
        return None

    match = _SELECT_OPTION.match(raw)
    if match is None:
        return None

    option = _clean(match.group("option"))
    target = _clean(match.group("target"))

    if not option or not target or not _looks_like_select_target(target):
        return None

    if _is_sensitive_target(target):
        return None

    return StructuredOptionSelectionRequest(target=target, option=option)


def is_contextual_form_attempt(command: str) -> bool:
    raw = command.strip()
    if not raw:
        return False
    return _FILL_HINT.search(raw) is not None and _SELECT_HINT.search(raw) is not None


def _extract_fill_requests(command: str) -> tuple[StructuredTextInputRequest, ...]:
    form: StructuredFormRequest | None = extract_structured_form(command)
    if form is not None:
        return form.fields

    single = extract_structured_text_input(command)
    return (single,) if single is not None else ()


def extract_contextual_form(
    command: str,
) -> StructuredContextualFormRequest | None:
    """Extrai um formulário com preenchimento + seleção no mesmo contexto.

    Exemplo aceito::

        preencha o campo nome com Ssamir e o campo cidade com Manaus
        e selecione Amazonas no campo estado
    """

    raw = command.strip()
    if not raw or not is_contextual_form_attempt(raw):
        return None

    selection_start = _SELECTION_START.search(raw)
    if selection_start is None:
        return None

    fill_part = raw[: selection_start.start()].strip().rstrip(" ,;")
    selection_part = raw[selection_start.end():].strip()

    fields = _extract_fill_requests(fill_part)
    if not fields:
        return None

    if any(_is_sensitive_target(field.target) for field in fields):
        return None

    selection_chunks = tuple(
        part.strip().rstrip(" .!?;:").strip()
        for part in _SELECTION_SPLIT.split(selection_part)
        if part.strip()
    )
    if not 1 <= len(selection_chunks) <= _MAX_SELECTIONS:
        return None

    selections: list[StructuredOptionSelectionRequest] = []
    for chunk in selection_chunks:
        selection = extract_structured_option_selection(chunk)
        if selection is None:
            return None
        selections.append(selection)

    if len(fields) + len(selections) > _MAX_CONTEXTUAL_OPERATIONS:
        return None

    normalized_targets = [
        _normalize(item.target)
        for item in (*fields, *selections)
    ]
    if len(set(normalized_targets)) != len(normalized_targets):
        return None

    return StructuredContextualFormRequest(
        fields=fields,
        selections=tuple(selections),
    )
