from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from atlas.vision.models import ScreenCapture


class ScreenshotImage(Protocol):
    size: tuple[int, int]

    def save(self, path: str | Path) -> None:
        ...


ScreenshotProvider = Callable[[], ScreenshotImage]


class ScreenCaptureError(RuntimeError):
    """Falha controlada durante uma captura visual."""


class ScreenCaptureService:
    """Captura a tela sem acoplar Vision ao Planner ou ao Executor."""

    def __init__(
        self,
        output_dir: Path,
        *,
        screenshot_provider: ScreenshotProvider | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self._screenshot_provider = screenshot_provider

    def capture_primary_screen(self) -> ScreenCapture:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        provider = self._screenshot_provider or self._default_provider

        try:
            image = provider()
            width, height = image.size
            captured_at = datetime.now()
            filename = (
                "screen_"
                f"{captured_at.strftime('%Y%m%d_%H%M%S_%f')}.png"
            )
            path = self.output_dir / filename
            image.save(path)
        except Exception as error:
            raise ScreenCaptureError(
                f"Não foi possível capturar a tela: {error}"
            ) from error

        if width <= 0 or height <= 0:
            path.unlink(missing_ok=True)
            raise ScreenCaptureError(
                "A captura retornou dimensões inválidas."
            )

        return ScreenCapture(
            path=path,
            width=width,
            height=height,
            captured_at=captured_at,
        )

    @staticmethod
    def _default_provider() -> ScreenshotImage:
        import pyautogui

        return pyautogui.screenshot()
