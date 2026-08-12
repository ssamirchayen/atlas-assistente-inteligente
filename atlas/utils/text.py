from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def remove_wake_word(
    text: str,
    wake_word: str,
) -> tuple[bool, str]:
    normalized_text = normalize(text)
    normalized_wake = normalize(wake_word)

    # Inclui variações que o reconhecimento de voz pode produzir.
    wake_variations = [
        normalized_wake,
        "atras",
    ]

    wake_expression = "|".join(
        re.escape(variation)
        for variation in wake_variations
    )

    patterns = [
        rf"^(?:{wake_expression})\b",
        rf"^(?:ok|ei|ola|alô|alo)\s+(?:{wake_expression})\b",
        rf"^(?:por favor)\s+(?:{wake_expression})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized_text)

        if not match:
            continue

        cleaned = re.sub(
            pattern,
            "",
            normalized_text,
            count=1,
        ).strip()

        cleaned = re.sub(
            r"^(por favor|pode|poderia|voce pode)\s+",
            "",
            cleaned,
        )

        return True, cleaned.strip()

    return False, normalized_text


def clean_politeness(text: str) -> str:
    text = normalize(text)

    text = re.sub(
        r"^(por favor|pode|poderia|voce pode|faz o favor de)\s+",
        "",
        text,
    )

    return text.strip()