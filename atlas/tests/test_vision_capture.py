from pathlib import Path

import pytest

from atlas.vision.capture import (
    ScreenCaptureError,
    ScreenCaptureService,
)


class FakeImage:
    def __init__(self, size: tuple[int, int] = (1920, 1080)) -> None:
        self.size = size

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(b"fake-png")


def test_capture_creates_local_artifact(tmp_path: Path) -> None:
    service = ScreenCaptureService(
        tmp_path,
        screenshot_provider=FakeImage,
    )

    capture = service.capture_primary_screen()

    assert capture.path.exists()
    assert capture.size == (1920, 1080)
    assert capture.source == "primary_screen"
    assert capture.path.parent == tmp_path


def test_capture_rejects_invalid_dimensions(tmp_path: Path) -> None:
    service = ScreenCaptureService(
        tmp_path,
        screenshot_provider=lambda: FakeImage((0, 1080)),
    )

    with pytest.raises(ScreenCaptureError):
        service.capture_primary_screen()


def test_capture_wraps_provider_failure(tmp_path: Path) -> None:
    def fail():
        raise RuntimeError("display unavailable")

    service = ScreenCaptureService(
        tmp_path,
        screenshot_provider=fail,
    )

    with pytest.raises(ScreenCaptureError) as error:
        service.capture_primary_screen()

    assert "display unavailable" in str(error.value)
