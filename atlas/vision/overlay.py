from __future__ import annotations

from dataclasses import dataclass

from atlas.vision.models import VisionGroundingResult


@dataclass(frozen=True, slots=True)
class VisionOverlaySpec:
    """Descrição read-only da marca visual exibida na tela."""

    label: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = 0.0
    duration_ms: int = 2800

    @classmethod
    def from_grounding(
        cls,
        result: VisionGroundingResult,
    ) -> VisionOverlaySpec | None:
        if (
            not result.found
            or result.element is None
            or result.element.bbox is None
        ):
            return None

        box = result.element.bbox

        return cls(
            label=result.element.label or result.query,
            x1=box.x1,
            y1=box.y1,
            x2=box.x2,
            y2=box.y2,
            confidence=result.element.confidence,
        )

    def rect_for_size(
        self,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int]:
        """Converte bbox normalizada em geometria lógica da tela."""

        left = round(self.x1 * width / 1000)
        top = round(self.y1 * height / 1000)
        right = round(self.x2 * width / 1000)
        bottom = round(self.y2 * height / 1000)

        return (
            left,
            top,
            max(1, right - left),
            max(1, bottom - top),
        )

    def center_for_size(
        self,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        x, y, box_width, box_height = self.rect_for_size(
            width,
            height,
        )
        return (
            x + box_width // 2,
            y + box_height // 2,
        )
