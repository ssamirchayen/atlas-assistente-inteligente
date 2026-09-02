from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from atlas.vision.models import (
    VisionBoundingBox,
    VisionGroundingResult,
    VisionUIElement,
)

if TYPE_CHECKING:
    from atlas.automation.browser import BrowserAutomation


@dataclass(frozen=True, slots=True)
class BrowserDomMatch:
    grounding: VisionGroundingResult
    dom_index: int
    confidence: float
    fingerprint: dict[str, str]
    semantic_kind: str = ""

    def click_fingerprint(self) -> dict[str, str]:
        return dict(self.fingerprint)


_STOPWORDS = {
    "a",
    "ao",
    "botao",
    "campo",
    "caixa",
    "da",
    "de",
    "do",
    "em",
    "esta",
    "fica",
    "na",
    "no",
    "o",
    "onde",
}

_SEMANTIC = {
    "busca": "search",
    "buscar": "search",
    "pesquisa": "search",
    "pesquisar": "search",
    "search": "search",
    "enviar": "send",
    "submit": "send",
    "send": "send",
    "entrar": "login",
    "login": "login",
    "acessar": "login",
}

_SEARCH_CONTAINER_WORDS = {
    "campo",
    "barra",
    "caixa",
    "input",
    "entrada",
}

_SEARCH_WORDS = {
    "busca",
    "buscar",
    "pesquisa",
    "pesquisar",
    "search",
}

_TEXT_ENTRY_TAGS = {
    "input",
    "textarea",
}

_TEXT_ENTRY_ROLES = {
    "searchbox",
    "textbox",
    "combobox",
}

_NON_ENTRY_ROLES = {
    "button",
    "link",
    "menuitem",
    "tab",
}

_NON_ENTRY_TAGS = {
    "a",
    "button",
}


def _normalize(text: object) -> str:
    value = unicodedata.normalize(
        "NFKD",
        str(text or "").lower(),
    )
    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )
    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )
    return " ".join(value.split())


def _tokens(text: object) -> list[str]:
    result: list[str] = []

    for token in _normalize(text).split():
        if token in _STOPWORDS:
            continue
        result.append(
            _SEMANTIC.get(token, token)
        )

    return result


def _candidate_text(
    candidate: dict[str, Any],
) -> str:
    return " ".join(
        str(candidate.get(key, "") or "")
        for key in (
            "aria_label",
            "labels",
            "placeholder",
            "title",
            "text",
            "name",
            "role",
            "type",
            "tag",
        )
    )


def _is_search_entry_request(query: str) -> bool:
    raw = _normalize(query)
    words = set(raw.split())

    has_search_word = bool(
        words & _SEARCH_WORDS
    )
    has_container_word = bool(
        words & _SEARCH_CONTAINER_WORDS
    )

    # Também cobre frases como:
    # "onde eu digito no google?"
    typing_language = any(
        phrase in raw
        for phrase in (
            "onde eu digito",
            "onde digito",
            "onde escrever",
            "onde eu escrevo",
            "onde pesquisar",
            "onde buscar",
        )
    )

    return (
        has_search_word
        and has_container_word
    ) or typing_language


def _semantic_kind(
    query: str,
) -> str:
    if _is_search_entry_request(query):
        return "search_input"

    raw = _normalize(query)

    if any(term in raw for term in ("checkbox", "caixa de selecao")):
        return "checkbox"

    if any(term in raw for term in ("botao de opcao", "radio", "opcao")):
        return "radio"

    if any(term in raw for term in ("switch", "interruptor")):
        return "switch"

    if "botao" in raw:
        return "button"

    if any(
        term in raw
        for term in (
            "campo",
            "barra",
            "caixa",
            "digito",
            "escrevo",
        )
    ):
        return "text_input"

    return ""


def _search_input_bonus(
    candidate: dict[str, Any],
) -> float:
    tag = _normalize(
        candidate.get("tag")
    )
    role = _normalize(
        candidate.get("role")
    )
    input_type = _normalize(
        candidate.get("type")
    )
    name = _normalize(
        candidate.get("name")
    )
    aria_label = _normalize(
        candidate.get("aria_label")
    )
    placeholder = _normalize(
        candidate.get("placeholder")
    )

    bonus = 0.0

    if role == "searchbox":
        bonus += 0.55
    if name == "q":
        bonus += 0.50
    if tag == "textarea":
        bonus += 0.38
    if tag == "input":
        bonus += 0.30
    if role == "combobox":
        bonus += 0.30
    if role == "textbox":
        bonus += 0.28
    if input_type == "search":
        bonus += 0.42

    if any(
        term in aria_label
        for term in (
            "pesquisar",
            "pesquisa",
            "buscar",
            "busca",
            "search",
        )
    ):
        bonus += 0.28

    if any(
        term in placeholder
        for term in (
            "pesquisar",
            "pesquisa",
            "buscar",
            "busca",
            "search",
        )
    ):
        bonus += 0.26

    return bonus


def _is_text_entry(
    candidate: dict[str, Any],
) -> bool:
    tag = _normalize(
        candidate.get("tag")
    )
    role = _normalize(
        candidate.get("role")
    )
    input_type = _normalize(
        candidate.get("type")
    )

    if tag in _TEXT_ENTRY_TAGS:
        return input_type not in {
            "button",
            "checkbox",
            "hidden",
            "radio",
            "submit",
        }

    return role in _TEXT_ENTRY_ROLES


def _base_similarity(
    query: str,
    candidate: dict[str, Any],
) -> float:
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(
        _candidate_text(candidate)
    )

    if not query_tokens or not candidate_tokens:
        return 0.0

    token_scores: list[float] = []

    for query_token in query_tokens:
        best = max(
            SequenceMatcher(
                None,
                query_token,
                candidate_token,
            ).ratio()
            for candidate_token in candidate_tokens
        )
        token_scores.append(best)

    score = sum(token_scores) / len(token_scores)

    query_norm = " ".join(query_tokens)
    candidate_norm = " ".join(
        candidate_tokens
    )

    return max(
        score,
        SequenceMatcher(
            None,
            query_norm,
            candidate_norm,
        ).ratio(),
    )


def _score(
    query: str,
    candidate: dict[str, Any],
) -> float:
    score = _base_similarity(
        query,
        candidate,
    )

    if score <= 0.0:
        return 0.0

    raw_query = _normalize(query)
    role = _normalize(
        candidate.get("role")
    )
    tag = _normalize(
        candidate.get("tag")
    )
    input_type = _normalize(
        candidate.get("type")
    )
    name = _normalize(
        candidate.get("name")
    )
    aria_label = _normalize(
        candidate.get("aria_label")
    )
    placeholder = _normalize(
        candidate.get("placeholder")
    )
    text = _normalize(
        candidate.get("text")
    )

    candidate_tokens = set(
        _tokens(
            _candidate_text(candidate)
        )
    )

    search_entry_request = (
        _is_search_entry_request(query)
    )

    # --------------------------------------------------------------
    # INTENÇÃO: CAMPO/BARRA/CAIXA DE PESQUISA
    # --------------------------------------------------------------
    if search_entry_request:
        if _is_text_entry(candidate):
            score += 0.34

        if role == "searchbox":
            score += 0.32

        if role in {
            "textbox",
            "combobox",
        }:
            score += 0.18

        if tag in _TEXT_ENTRY_TAGS:
            score += 0.18

        if input_type == "search":
            score += 0.28

        # Padrão extremamente comum em motores de busca.
        if name == "q":
            score += 0.22

        if "search" in candidate_tokens:
            score += 0.16

        if any(
            term in aria_label
            for term in (
                "pesquisar",
                "pesquisa",
                "buscar",
                "busca",
                "search",
            )
        ):
            score += 0.16

        if any(
            term in placeholder
            for term in (
                "pesquisar",
                "pesquisa",
                "buscar",
                "busca",
                "search",
            )
        ):
            score += 0.16

        # Se o usuário pediu um lugar para digitar, links/botões não
        # devem vencer apenas porque contêm "Pesquisar".
        if (
            role in _NON_ENTRY_ROLES
            or tag in _NON_ENTRY_TAGS
        ):
            score -= 0.55

        if input_type in {
            "button",
            "submit",
        }:
            score -= 0.45

        # Casos típicos do Google:
        # "Pesquisar imagens", "Pesquisa por voz", "Pesquisa por imagem".
        if any(
            phrase in text
            or phrase in aria_label
            for phrase in (
                "pesquisar imagens",
                "pesquisa por imagem",
                "pesquisa por voz",
                "search by image",
                "voice search",
                "google apps",
            )
        ):
            score -= 0.48

    # --------------------------------------------------------------
    # INTENÇÃO GENÉRICA DE CAMPO
    # --------------------------------------------------------------
    elif any(
        term in raw_query
        for term in (
            "campo",
            "caixa",
            "barra",
        )
    ):
        if _is_text_entry(candidate):
            score += 0.18

        if (
            role in _NON_ENTRY_ROLES
            or tag in _NON_ENTRY_TAGS
        ):
            score -= 0.18

    # --------------------------------------------------------------
    # INTENÇÃO DE BOTÃO
    # --------------------------------------------------------------
    if "botao" in raw_query:
        if (
            tag == "button"
            or role == "button"
            or input_type
            in {
                "button",
                "submit",
            }
        ):
            score += 0.22
        elif _is_text_entry(candidate):
            score -= 0.18

    # --------------------------------------------------------------
    # INTENÇÃO DE CONTROLE DE ESTADO (ETAPA 13)
    # --------------------------------------------------------------
    wants_checkbox = any(
        term in raw_query
        for term in ("checkbox", "caixa de selecao", "interruptor", "switch")
    )
    wants_radio = any(
        term in raw_query
        for term in ("botao de opcao", "radio", "opcao")
    )
    if wants_checkbox:
        if input_type == "checkbox" or role in {"checkbox", "switch"}:
            score += 0.42
        elif input_type == "radio":
            score -= 0.35

    if wants_radio:
        if input_type == "radio" or role == "radio":
            score += 0.42
        elif input_type == "checkbox" or role in {"checkbox", "switch"}:
            score -= 0.35

    return max(
        0.0,
        min(score, 1.0),
    )


def find_browser_dom_match(
    browser: BrowserAutomation,
    query: str,
    *,
    screen_width: int,
    screen_height: int,
) -> BrowserDomMatch | None:
    """Retorna grounding + identidade DOM para uma ação controlada."""

    candidates = (
        browser.inspect_visible_interactive_elements()
    )

    if not candidates:
        return None

    semantic_kind = _semantic_kind(query)

    ranked = sorted(
        (
            (
                min(
                    1.0,
                    _score(query, candidate)
                    + (
                        _search_input_bonus(candidate)
                        if semantic_kind == "search_input"
                        else 0.0
                    ),
                ),
                candidate,
            )
            for candidate in candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    if not ranked:
        return None

    confidence, best = ranked[0]

    if semantic_kind == "search_input" and not _is_text_entry(best):
        for candidate_confidence, candidate in ranked[1:]:
            if (
                candidate_confidence >= 0.63
                and _is_text_entry(candidate)
            ):
                confidence = candidate_confidence
                best = candidate
                break

    if confidence < 0.63:
        return None

    try:
        dom_index = int(best["dom_index"])
        left = float(best["left"])
        top = float(best["top"])
        right = float(best["right"])
        bottom = float(best["bottom"])
    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        return None

    left = max(
        0.0,
        min(left, float(screen_width)),
    )
    right = max(
        0.0,
        min(right, float(screen_width)),
    )
    top = max(
        0.0,
        min(top, float(screen_height)),
    )
    bottom = max(
        0.0,
        min(bottom, float(screen_height)),
    )

    if right <= left or bottom <= top:
        return None

    try:
        bbox = VisionBoundingBox(
            round(
                left * 1000 / screen_width
            ),
            round(
                top * 1000 / screen_height
            ),
            round(
                right * 1000 / screen_width
            ),
            round(
                bottom * 1000 / screen_height
            ),
        )
    except ValueError:
        return None

    label = next(
        (
            str(
                best.get(key, "")
            ).strip()
            for key in (
                "aria_label",
                "labels",
                "placeholder",
                "text",
                "name",
            )
            if str(
                best.get(key, "")
            ).strip()
        ),
        query,
    )

    kind = (
        str(
            best.get("role", "")
        ).strip()
        or str(
            best.get("tag", "")
        ).strip()
        or "dom"
    )

    grounding = VisionGroundingResult(
        query=query,
        found=True,
        element=VisionUIElement(
            label=label,
            kind=kind,
            description=(
                "Elemento localizado diretamente "
                "pelo DOM da página do navegador."
            ),
            bbox=bbox,
            confidence=confidence,
        ),
        message=(
            f"Localizei '{label}' "
            "diretamente pelo DOM."
        ),
    )

    fingerprint = {
        key: str(
            best.get(key, "") or ""
        ).strip()
        for key in (
            "tag",
            "role",
            "type",
            "name",
            "aria_label",
            "placeholder",
            "title",
            "text",
        )
    }

    return BrowserDomMatch(
        grounding=grounding,
        dom_index=dom_index,
        confidence=confidence,
        fingerprint=fingerprint,
        semantic_kind=semantic_kind,
    )


def locate_browser_dom_element(
    browser: BrowserAutomation,
    query: str,
    *,
    screen_width: int,
    screen_height: int,
) -> VisionGroundingResult | None:
    """Mantém a API read-only usada pelo grounding da Etapa 5."""

    match = find_browser_dom_match(
        browser,
        query,
        screen_width=screen_width,
        screen_height=screen_height,
    )

    if match is None:
        return None

    return match.grounding
