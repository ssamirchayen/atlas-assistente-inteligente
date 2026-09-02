from datetime import datetime
from pathlib import Path

from atlas.vision.models import (
    ScreenCapture,
    VisionAnalysis,
)
from atlas.vision.service import VisionService


class FakeCaptureService:
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
    def analyze(self, path: Path, *, question: str) -> VisionAnalysis:
        assert path.exists()
        assert question
        return VisionAnalysis(
            summary="Tela de teste.",
            confidence=0.9,
            model="fake",
        )


def test_service_removes_capture_by_default(
    tmp_path: Path,
) -> None:
    path = tmp_path / "screen.png"
    service = VisionService(
        FakeCaptureService(path),
        FakeAnalyzer(),
        keep_captures=False,
    )

    result = service.observe_screen()

    assert result.analysis.summary == "Tela de teste."
    assert not path.exists()


def test_service_can_keep_capture(tmp_path: Path) -> None:
    path = tmp_path / "screen.png"
    service = VisionService(
        FakeCaptureService(path),
        FakeAnalyzer(),
        keep_captures=True,
    )

    service.observe_screen()

    assert path.exists()
