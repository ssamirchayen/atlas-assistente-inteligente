"""Intenções explícitas para controles Windows via UI Automation.

A Etapa 9 mantém o princípio de ação única e estrutural: somente verbos
claramente associados a um controle de interface são aceitos aqui. Comandos
genéricos como ``abra o Google`` continuam fora deste parser para não roubar
rotas do SkillRouter/Planner.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowsUIAActionRequest:
    action: str
    target: str


_ACTION_PREFIX = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?P<verb>marque|marcar|desmarque|desmarcar|"
    r"selecione|seleciona|selecionar|"
    r"expanda|expandir|recolha|recolher|"
    r"foque|focar)"
    r"\s+(?:(?:no|na|nos|nas|em|o|a|os|as)\s+)?"
    r"(?P<target>.+?)\s*$",
    flags=re.IGNORECASE,
)

_OPEN_CLOSE_PREFIX = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?P<verb>abra|abre|abrir|feche|fecha|fechar)"
    r"\s+(?:(?:o|a|os|as|no|na|nos|nas)\s+)?"
    r"(?P<target>.+?)\s*$",
    flags=re.IGNORECASE,
)


_ACTION_BY_VERB = {
    "marque": "check",
    "marcar": "check",
    "desmarque": "uncheck",
    "desmarcar": "uncheck",
    "selecione": "select",
    "seleciona": "select",
    "selecionar": "select",
    "expanda": "expand",
    "expandir": "expand",
    "recolha": "collapse",
    "recolher": "collapse",
    "foque": "focus",
    "focar": "focus",
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.lower())
    value = "".join(
        char for char in value if not unicodedata.combining(char)
    )
    return " ".join(value.split())


def _clean_target(target: str) -> str:
    return target.rstrip(" .!?;:").strip()


_GENERIC_EXPANDABLE_TARGETS = {
    "menu",
    "lista",
    "combobox",
    "combo box",
    "caixa de combinacao",
    "painel",
}


def _is_generic_expandable_target(target: str) -> bool:
    return _normalize(target) in _GENERIC_EXPANDABLE_TARGETS


def _is_expandable_target(target: str) -> bool:
    normalized = _normalize(target)
    return any(
        marker in normalized
        for marker in (
            "menu",
            "lista",
            "combobox",
            "combo box",
            "caixa de combinacao",
            "painel",
        )
    )


def extract_windows_uia_action(
    command: str,
) -> WindowsUIAActionRequest | None:
    """Extrai uma única ação estrutural Windows explicitamente solicitada."""

    raw = command.strip()
    if not raw:
        return None

    normalized = _normalize(raw)
    if any(
        marker in normalized
        for marker in (
            " e depois ",
            " em seguida ",
            " depois ",
            " duas vezes",
        )
    ):
        return None

    match = _ACTION_PREFIX.match(raw)
    if match is not None:
        verb = _normalize(match.group("verb"))
        target = _clean_target(match.group("target"))
        action = _ACTION_BY_VERB.get(verb)
        if action and target:
            return WindowsUIAActionRequest(action=action, target=target)
        return None

    match = _OPEN_CLOSE_PREFIX.match(raw)
    if match is None:
        return None

    target = _clean_target(match.group("target"))
    if (
        not target
        or _is_generic_expandable_target(target)
        or not _is_expandable_target(target)
    ):
        return None

    verb = _normalize(match.group("verb"))
    action = "expand" if verb in {"abra", "abre", "abrir"} else "collapse"
    return WindowsUIAActionRequest(action=action, target=target)
