"""Normalização determinística de comandos vindos do ASR.

A camada de reconhecimento pode devolver palavras foneticamente próximas dos
verbos estruturais do Atlas (por exemplo ``quick`` no lugar de ``clique``).
Este módulo corrige apenas aliases conhecidos e de baixo risco. Ele não tenta
inventar alvos ausentes nem completar comandos por contexto.
"""

from __future__ import annotations

import re


_WORD_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    # O Google ASR costuma devolver "quick" para "clique" em pt-BR.
    (
        re.compile(r"^(?:quick|quique|click|clik)\b", re.IGNORECASE),
        "clique",
    ),
    (
        re.compile(r"^(?:clica|clicar)\b", re.IGNORECASE),
        "clique",
    ),
    (
        re.compile(r"^(?:digita|digitar)\b", re.IGNORECASE),
        "digite",
    ),
    (
        re.compile(r"^(?:abre|abrir)\b", re.IGNORECASE),
        "abra",
    ),
    (
        re.compile(r"^(?:seleciona|selecionar)\b", re.IGNORECASE),
        "selecione",
    ),
    (
        re.compile(r"^(?:marca|marcar)\b", re.IGNORECASE),
        "marque",
    ),
    (
        re.compile(r"^(?:desmarca|desmarcar)\b", re.IGNORECASE),
        "desmarque",
    ),
)

_PHRASE_REPAIRS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bbarra pesquisa\b", re.IGNORECASE),
        "barra de pesquisa",
    ),
    (
        re.compile(r"\bcampo pesquisa\b", re.IGNORECASE),
        "campo de pesquisa",
    ),
    (
        re.compile(r"\bcaixa pesquisa\b", re.IGNORECASE),
        "caixa de pesquisa",
    ),
    (
        re.compile(r"\bcampo texto\b", re.IGNORECASE),
        "campo de texto",
    ),
    (
        re.compile(r"\bbloco notas\b", re.IGNORECASE),
        "bloco de notas",
    ),
)

# Se o usuário explicitamente se corrige no mesmo áudio, é mais seguro não
# executar a primeira intenção. O listener ignora a frase e aguarda outra.
_SELF_CORRECTION = re.compile(
    r"\b(?:desculpa\s+errei|foi\s+mal\s+errei|nao\s+era\s+isso|"
    r"não\s+era\s+isso|cancela\s+isso|cancelar\s+isso)\b",
    re.IGNORECASE,
)


def normalize_voice_command(command: str) -> str:
    """Corrige aliases previsíveis do ASR sem adivinhar conteúdo ausente.

    Retorna string vazia quando a mesma fala contém uma autocorreção explícita,
    evitando executar uma intenção que o usuário acabou de invalidar.
    """

    value = " ".join(str(command or "").strip().split())
    if not value:
        return ""

    if _SELF_CORRECTION.search(value):
        return ""

    for pattern, replacement in _WORD_ALIASES:
        value = pattern.sub(replacement, value, count=1)

    for pattern, replacement in _PHRASE_REPAIRS:
        value = pattern.sub(replacement, value)

    return " ".join(value.split()).strip()
