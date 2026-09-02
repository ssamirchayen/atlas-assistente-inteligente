from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ScreenCapture:
    path: Path
    width: int
    height: int
    captured_at: datetime
    source: str = "primary_screen"

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


@dataclass(frozen=True, slots=True)
class VisionBoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def __post_init__(self) -> None:
        values = (self.x1, self.y1, self.x2, self.y2)

        if any(
            value < 0 or value > 1000
            for value in values
        ):
            raise ValueError(
                "Coordenadas normalizadas devem estar entre 0 e 1000."
            )

        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError(
                "Bounding box inválida."
            )

    @property
    def center(self) -> tuple[int, int]:
        """Centro da caixa em coordenadas normalizadas 0..1000."""

        return (
            (self.x1 + self.x2) // 2,
            (self.y1 + self.y2) // 2,
        )

    def to_pixels(
        self,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        return (
            round(self.x1 * width / 1000),
            round(self.y1 * height / 1000),
            round(self.x2 * width / 1000),
            round(self.y2 * height / 1000),
        )

    def center_pixels(
        self,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        x1, y1, x2, y2 = self.to_pixels(
            width,
            height,
        )

        return (
            (x1 + x2) // 2,
            (y1 + y2) // 2,
        )


@dataclass(frozen=True, slots=True)
class VisionUIElement:
    label: str
    kind: str = "unknown"
    description: str = ""
    bbox: VisionBoundingBox | None = None
    confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class VisionAnalysis:
    summary: str
    visible_text: tuple[str, ...] = ()
    applications: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    ui_elements: tuple[VisionUIElement, ...] = ()
    confidence: float = 0.0
    model: str = ""
    raw_response: str = ""

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


@dataclass(frozen=True, slots=True)
class VisionObservation:
    capture: ScreenCapture
    analysis: VisionAnalysis


@dataclass(frozen=True, slots=True)
class VisionGroundingResult:
    query: str
    found: bool
    element: VisionUIElement | None = None
    message: str = ""

    def center_pixels(
        self,
        width: int,
        height: int,
    ) -> tuple[int, int] | None:
        if (
            self.element is None
            or self.element.bbox is None
        ):
            return None

        return self.element.bbox.center_pixels(
            width,
            height,
        )
