from __future__ import annotations

import re
import unicodedata


_CLICK_PREFIX = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?:clique|clica|clicar|pressione|aperte|toque)"
    r"\s+(?:(?:no|na|nos|nas|em|o|a)\s+)?"
    r"(?P<target>.+?)\s*$",
    flags=re.IGNORECASE,
)


def _normalize(text: str) -> str:
    value = unicodedata.normalize(
        "NFKD",
        text.lower(),
    )
    return "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )


def extract_click_target(
    command: str,
) -> str | None:
    """Extrai somente um clique explicitamente pedido pelo usuário."""

    raw = command.strip()

    if not raw:
        return None

    normalized = _normalize(raw)

    # Etapa 6 executa apenas UM clique por comando.
    if any(
        marker in normalized
        for marker in (
            "duplo clique",
            "clique duas vezes",
            "double click",
            " e depois ",
            " depois clique ",
            " em seguida ",
        )
    ):
        return None

    match = _CLICK_PREFIX.match(raw)

    if match is None:
        return None

    target = match.group("target").strip()
    target = target.rstrip(" .!?;:").strip()

    if not target:
        return None

    return target
