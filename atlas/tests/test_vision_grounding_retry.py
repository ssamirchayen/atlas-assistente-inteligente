from datetime import datetime
from pathlib import Path

from atlas.vision.models import (
    ScreenCapture,
    VisionAnalysis,
    VisionBoundingBox,
    VisionUIElement,
)
from atlas.vision.service import VisionService


class FakeCapture:
    def __init__(self, path: Path) -> None:
        self.path = path

    def capture_primary_screen(self) -> ScreenCapture:
        self.path.write_bytes(b"image")
        return ScreenCapture(
            path=self.path,
            width=1920,
            height=1080,
            captured_at=datetime.now(),
        )


class FakeAnalyzer:
    def analyze(self, path: Path, *, question: str):
        return VisionAnalysis(
            summary="Interface",
            ui_elements=(
                VisionUIElement(
                    label="Enviar",
                    kind="button",
                    confidence=0.95,
                    bbox=None,
                ),
            ),
        )

    def locate_target(self, path: Path, *, target: str):
        return VisionUIElement(
            label="Enviar",
            kind="button",
            bbox=VisionBoundingBox(
                900,
                850,
                980,
                930,
            ),
            confidence=0.98,
        )


def test_grounding_retries_when_bbox_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "screen.png"
    service = VisionService(
        FakeCapture(path),
        FakeAnalyzer(),
        keep_captures=False,
    )

    observation, result = service.locate_on_screen(
        "botão enviar"
    )

    assert observation.capture.width == 1920
    assert result.found is True
    assert result.element is not None
    assert result.element.bbox is not None
    assert not path.exists()
