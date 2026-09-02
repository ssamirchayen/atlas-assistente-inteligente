from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DirectUrlRequest:
    """Pedido explícito para abrir uma URL HTTP(S) no navegador do Atlas."""

    url: str


_URL_RE = re.compile(r"(?P<url>https?://[^\s]+)", re.IGNORECASE)
_ALLOWED_PREFIXES = (
    "abra",
    "abrir",
    "abre",
    "acesse",
    "acessar",
    "acesa",
    "navegue para",
    "navegar para",
    "va para",
    "ir para",
)
_ALLOWED_SUFFIXES = {
    "",
    "por favor",
    "por gentileza",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.casefold().strip().split())


def _strip_trailing_sentence_punctuation(url: str) -> str:
    # Pontuação de fim de frase não faz parte da URL falada/digitada na GUI.
    # Não removemos caracteres válidos internos de path/query/fragment.
    return url.rstrip(".,;!?")


def extract_direct_url_command(command: str) -> DirectUrlRequest | None:
    """Extrai apenas comandos explícitos e simples de abertura de HTTP(S).

    Exemplos aceitos:
    - ``abra http://127.0.0.1:8765/tools/lab.html``
    - ``acesse https://example.com/path?q=1``

    Cadeias como ``abra <url> e depois ...`` não são consumidas aqui para não
    descartar silenciosamente um segundo passo.
    """

    text = command.strip()
    match = _URL_RE.search(text)
    if match is None:
        return None

    prefix = _normalize(text[: match.start()].strip(" ,:-"))
    if not any(
        prefix == allowed or prefix.endswith(f" {allowed}")
        for allowed in _ALLOWED_PREFIXES
    ):
        return None

    suffix = _normalize(text[match.end() :].strip(" ,.;:!?-"))
    if suffix not in _ALLOWED_SUFFIXES:
        return None

    url = _strip_trailing_sentence_punctuation(match.group("url"))
    if not url.lower().startswith(("http://", "https://")):
        return None

    return DirectUrlRequest(url=url)
