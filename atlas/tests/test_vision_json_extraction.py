import pytest

from atlas.vision.analyzer import (
    OllamaVisionAnalyzer,
    VisionAnalysisError,
)


def test_extracts_pure_json() -> None:
    payload = OllamaVisionAnalyzer._extract_json_object(
        '{"label":"Enviar","bbox":[900,850,980,930]}'
    )

    assert payload["label"] == "Enviar"


def test_extracts_json_from_markdown_fence() -> None:
    payload = OllamaVisionAnalyzer._extract_json_object(
        '```json\n{"label":"Enviar","bbox":[900,850,980,930]}\n```'
    )

    assert payload["label"] == "Enviar"


def test_extracts_json_with_text_around_it() -> None:
    payload = OllamaVisionAnalyzer._extract_json_object(
        'Aqui está o resultado:\n'
        '{"label":"Enviar","bbox":[900,850,980,930],"confidence":0.98}\n'
        'Fim.'
    )

    assert payload["confidence"] == 0.98


def test_extracts_nested_json_object() -> None:
    payload = OllamaVisionAnalyzer._extract_json_object(
        'Resultado: {"label":"Enviar","meta":{"kind":"button"},'
        '"bbox":[900,850,980,930]}'
    )

    assert payload["meta"]["kind"] == "button"


def test_rejects_non_json_text() -> None:
    with pytest.raises(VisionAnalysisError):
        OllamaVisionAnalyzer._extract_json_object(
            "Não encontrei nenhum botão."
        )
