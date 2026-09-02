from __future__ import annotations

import re
import unicodedata


_ACTION_WORDS = (
    "clique",
    "clicar",
    "aperte",
    "pressione",
    "digite",
    "escreva",
    "abra",
    "feche",
    "arraste",
    "execute",
)

_READ_ONLY_PATTERNS = (
    r"\bo que (?:voce )?(?:esta )?vendo\b",
    r"\bo que (?:voce )?ve\b",
    r"\bo que (?:esta|tem|aparece) (?:na|nessa|nesta)? ?tela\b",
    r"\btem (?:algum )?erro(?: ai| nessa tela| na tela)?\b",
    r"\bha (?:algum )?erro(?: ai| nessa tela| na tela)?\b",
    r"\bqual (?:programa|aplicativo|janela) (?:esta|ta) aberto\b",
    r"\bo que (?:esta|ta) escrito(?: aqui| na tela| nessa tela)?\b",
    r"\bdescrev[ae] (?:a|minha|essa|esta)? ?tela\b",
    r"\banalis[ae] (?:a|minha|essa|esta)? ?tela\b",
    r"\bolha (?:a|minha|essa|esta)? ?tela\b",
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text)


def is_read_only_vision_command(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False

    if any(re.search(rf"\b{w}\b", normalized) for w in _ACTION_WORDS):
        return False

    return any(re.search(p, normalized) for p in _READ_ONLY_PATTERNS)
