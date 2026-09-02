from __future__ import annotations

import re
import unicodedata


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text)


def extract_grounding_query(text: str) -> str | None:
    normalized = _normalize(text)

    action_words = (
        "clique", "clicar", "aperte", "pressione",
        "digite", "abra", "feche", "arraste", "execute",
    )
    if any(
        re.search(rf"\b{word}\b", normalized)
        for word in action_words
    ):
        return None

    patterns = (
        r"^onde (?:esta|fica) (?:o|a)? ?(.+)$",
        r"^localize (?:o|a)? ?(.+)$",
        r"^encontre (?:o|a)? ?(.+) na tela$",
        r"^mostre onde (?:esta|fica) (?:o|a)? ?(.+)$",
    )

    for pattern in patterns:
        match = re.match(pattern, normalized)
        if match:
            query = match.group(1).strip()
            return query or None

    return None
