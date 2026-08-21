from atlas.voice.response import (
    normalize_spoken_text,
    sentence_pause_seconds,
    split_for_speech,
)


def test_normalize_spoken_text_removes_visual_markdown() -> None:
    text = normalize_spoken_text(
        "## API\n- **FastAPI**: veja [documentação](https://example.com)."
    )

    assert "#" not in text
    assert "**" not in text
    assert "https://" not in text
    assert "FastAPI" in text
    assert "documentação" in text


def test_long_sentence_prefers_comma_boundary() -> None:
    message = (
        "Uma API conecta sistemas e permite troca de dados, "
        "ela também pode aplicar autenticação e regras de acesso, "
        "e isso facilita integrações empresariais complexas."
    )

    chunks = split_for_speech(message, max_chars=90)

    assert len(chunks) >= 2
    assert "".join(chunks).replace(" ", "") == message.replace(" ", "")


def test_sentence_pause_is_short_and_punctuation_aware() -> None:
    period = sentence_pause_seconds("Tudo certo.", base_ms=100)
    comma = sentence_pause_seconds("Primeiro,", base_ms=100)
    question = sentence_pause_seconds("Entendeu?", base_ms=100)

    assert comma < period < question
    assert period == 0.1
