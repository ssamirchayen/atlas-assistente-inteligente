from atlas.core.config import (
    VISION_CAPTURE_DIR,
    VISION_KEEP_CAPTURES,
)
from atlas.vision.analyzer import OllamaVisionAnalyzer
from atlas.vision.capture import ScreenCaptureService
from atlas.vision.formatter import describe_grounding
from atlas.vision.service import VisionService


def main() -> None:
    target = input("Elemento para localizar: ").strip()
    if not target:
        raise SystemExit("Informe um elemento.")

    service = VisionService(
        ScreenCaptureService(VISION_CAPTURE_DIR),
        OllamaVisionAnalyzer(),
        keep_captures=VISION_KEEP_CAPTURES,
    )

    observation, result = service.locate_on_screen(target)

    print()
    print(
        describe_grounding(
            result,
            width=observation.capture.width,
            height=observation.capture.height,
        )
    )

    if result.element and result.element.bbox:
        print("BBox normalizada:", result.element.bbox)
        print(
            "BBox pixels:",
            result.element.bbox.to_pixels(
                observation.capture.width,
                observation.capture.height,
            ),
        )


if __name__ == "__main__":
    main()
