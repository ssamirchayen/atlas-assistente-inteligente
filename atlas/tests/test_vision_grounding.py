from atlas.vision.grounding import locate_ui_element
from atlas.vision.models import (
    VisionAnalysis,
    VisionBoundingBox,
    VisionUIElement,
)


def test_bbox_converts_to_pixels() -> None:
    box = VisionBoundingBox(100, 200, 300, 400)

    assert box.to_pixels(1920, 1080) == (
        192,
        216,
        576,
        432,
    )
    assert box.center_pixels(1920, 1080) == (
        384,
        324,
    )


def test_locate_ui_element_selects_matching_button() -> None:
    analysis = VisionAnalysis(
        summary="Interface",
        ui_elements=(
            VisionUIElement(
                label="Histórico",
                kind="button",
                bbox=VisionBoundingBox(
                    700,
                    100,
                    780,
                    150,
                ),
                confidence=0.9,
            ),
            VisionUIElement(
                label="Enviar",
                kind="button",
                description=(
                    "Botão azul no canto inferior direito"
                ),
                bbox=VisionBoundingBox(
                    900,
                    850,
                    980,
                    930,
                ),
                confidence=0.96,
            ),
        ),
    )

    result = locate_ui_element(
        analysis,
        "botão enviar",
    )

    assert result.found is True
    assert result.element is not None
    assert result.element.label == "Enviar"


def test_locate_requires_bbox() -> None:
    analysis = VisionAnalysis(
        summary="Interface",
        ui_elements=(
            VisionUIElement(
                label="Enviar",
                kind="button",
                confidence=0.9,
            ),
        ),
    )

    result = locate_ui_element(
        analysis,
        "enviar",
    )

    assert result.found is False
