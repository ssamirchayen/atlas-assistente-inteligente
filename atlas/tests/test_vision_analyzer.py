from pathlib import Path

import pytest

from atlas.vision.analyzer import (
    OllamaVisionAnalyzer,
    VisionAnalysisError,
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "message": {
                "content": self._content,
            }
        }


def test_analyzer_sends_image_and_parses_json(
    tmp_path: Path,
) -> None:
    image = tmp_path / "screen.png"
    image.write_bytes(b"png-bytes")
    captured = {}

    def fake_post(url, *, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(
            """
            {
              "summary": "PowerShell aberto.",
              "visible_text": ["All checks passed"],
              "applications": ["Windows PowerShell"],
              "errors": [],
              "ui_elements": [
                {
                  "label": "terminal",
                  "kind": "window",
                  "description": "Janela do PowerShell",
                  "bbox": [10, 20, 990, 980],
                  "confidence": 0.93
                }
              ],
              "confidence": 0.91
            }
            """
        )

    analyzer = OllamaVisionAnalyzer(
        model="vision-test",
        url="http://localhost/api/chat",
        timeout=10,
        post=fake_post,
    )

    result = analyzer.analyze(image, question="O que há na tela?")

    assert result.summary == "PowerShell aberto."
    assert result.applications == ("Windows PowerShell",)
    assert result.visible_text == ("All checks passed",)
    assert result.confidence == 0.91
    assert result.ui_elements[0].kind == "window"
    assert result.ui_elements[0].bbox is not None
    assert result.ui_elements[0].confidence == 0.93
    assert captured["json"]["model"] == "vision-test"
    assert captured["json"]["messages"][0]["images"]


def test_analyzer_rejects_invalid_json(tmp_path: Path) -> None:
    image = tmp_path / "screen.png"
    image.write_bytes(b"x")

    analyzer = OllamaVisionAnalyzer(
        post=lambda *args, **kwargs: FakeResponse("não é json"),
    )

    with pytest.raises(VisionAnalysisError):
        analyzer.analyze(image)


def test_analyzer_requires_existing_image(tmp_path: Path) -> None:
    analyzer = OllamaVisionAnalyzer()

    with pytest.raises(VisionAnalysisError):
        analyzer.analyze(tmp_path / "missing.png")
