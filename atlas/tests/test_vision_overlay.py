from atlas.vision.models import (
    VisionBoundingBox,
    VisionGroundingResult,
    VisionUIElement,
)
from atlas.vision.overlay import VisionOverlaySpec


def test_overlay_from_grounding() -> None:
    result = VisionGroundingResult(
        query="botao enviar",
        found=True,
        element=VisionUIElement(
            label="Enviar",
            kind="button",
            bbox=VisionBoundingBox(
                800,
                700,
                900,
                800,
            ),
            confidence=0.93,
        ),
    )

    spec = VisionOverlaySpec.from_grounding(result)

    assert spec is not None
    assert spec.label == "Enviar"
    assert spec.rect_for_size(1920, 1080) == (
        1536,
        756,
        192,
        108,
    )
    assert spec.center_for_size(1920, 1080) == (
        1632,
        810,
    )


def test_overlay_requires_reliable_bbox() -> None:
    result = VisionGroundingResult(
        query="campo",
        found=True,
        element=VisionUIElement(
            label="Campo",
            bbox=None,
        ),
    )

    assert VisionOverlaySpec.from_grounding(result) is None
