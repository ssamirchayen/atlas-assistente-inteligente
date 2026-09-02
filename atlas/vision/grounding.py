from __future__ import annotations

import re
import unicodedata

from atlas.vision.models import (
    VisionAnalysis,
    VisionGroundingResult,
    VisionUIElement,
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    ignored = {
        "o", "a", "os", "as", "de", "da", "do",
        "em", "na", "no", "um", "uma", "botao",
        "campo", "menu", "onde", "esta", "fica",
    }
    return {
        token
        for token in _normalize(text).split()
        if token not in ignored
    }


def rank_element(
    query: str,
    element: VisionUIElement,
) -> float:
    query_tokens = _tokens(query)
    haystack = " ".join(
        (
            element.label,
            element.kind,
            element.description,
        )
    )
    element_tokens = _tokens(haystack)

    if not query_tokens:
        return element.confidence

    overlap = len(query_tokens & element_tokens)
    lexical = overlap / len(query_tokens)
    exact_bonus = (
        0.3
        if _normalize(query) in _normalize(haystack)
        else 0.0
    )
    bbox_bonus = 0.15 if element.bbox is not None else 0.0
    confidence_bonus = (
        max(0.0, min(element.confidence, 1.0))
        * 0.25
    )

    return (
        lexical
        + exact_bonus
        + bbox_bonus
        + confidence_bonus
    )


def locate_ui_element(
    analysis: VisionAnalysis,
    query: str,
    *,
    minimum_score: float = 0.45,
) -> VisionGroundingResult:
    candidates = [
        element
        for element in analysis.ui_elements
        if element.label.strip()
    ]

    if not candidates:
        return VisionGroundingResult(
            query=query,
            found=False,
            message=(
                "Não identifiquei elementos de interface suficientes."
            ),
        )

    ranked = sorted(
        (
            (rank_element(query, element), element)
            for element in candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    score, best = ranked[0]

    if score < minimum_score or best.bbox is None:
        return VisionGroundingResult(
            query=query,
            found=False,
            element=best,
            message=(
                "Encontrei um possível elemento, mas não tenho "
                "posição visual confiável."
            ),
        )

    return VisionGroundingResult(
        query=query,
        found=True,
        element=best,
        message=f"Localizei '{best.label}' na tela.",
    )
