from pathlib import Path

from atlas.vision.analyzer import OllamaVisionAnalyzer


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "message": {
                "content": self.content,
            }
        }


def test_locate_target_accepts_point_without_bbox(
    tmp_path: Path,
) -> None:
    image = tmp_path / "screen.png"
    image.write_bytes(b"png")

    analyzer = OllamaVisionAnalyzer(
        post=lambda *args, **kwargs: FakeResponse(
            """
            {
              "found": true,
              "label": "Enviar",
              "kind": "button",
              "bbox": null,
              "point": [940, 890],
              "confidence": 0.92
            }
            """
        )
    )

    element = analyzer.locate_target(
        image,
        target="botão enviar",
    )

    assert element is not None
    assert element.bbox is not None
    assert element.bbox.center == (940, 890)


def test_parse_point_accepts_percent_scale() -> None:
    assert OllamaVisionAnalyzer._parse_point(
        [94, 89]
    ) == (940, 890)
