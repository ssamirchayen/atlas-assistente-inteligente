from __future__ import annotations

from atlas.core.config import VISION_KEEP_CAPTURES
from atlas.vision.analyzer import OllamaVisionAnalyzer
from atlas.vision.capture import ScreenCaptureService
from atlas.vision.grounding import locate_ui_element
from atlas.vision.models import (
    VisionGroundingResult,
    VisionObservation,
)


class VisionService:
    def __init__(
        self,
        capture_service: ScreenCaptureService,
        analyzer: OllamaVisionAnalyzer,
        *,
        keep_captures: bool = VISION_KEEP_CAPTURES,
    ) -> None:
        self.capture_service = capture_service
        self.analyzer = analyzer
        self.keep_captures = keep_captures

    def observe_screen(
        self,
        question: str = "O que está visível na minha tela?",
    ) -> VisionObservation:
        capture = self.capture_service.capture_primary_screen()

        try:
            analysis = self.analyzer.analyze(
                capture.path,
                question=question,
            )
        finally:
            if not self.keep_captures:
                capture.path.unlink(missing_ok=True)

        return VisionObservation(
            capture=capture,
            analysis=analysis,
        )

    def locate_on_screen(
        self,
        query: str,
    ) -> tuple[
        VisionObservation,
        VisionGroundingResult,
    ]:
        capture = self.capture_service.capture_primary_screen()

        try:
            analysis = self.analyzer.analyze(
                capture.path,
                question=(
                    "Analise a tela com foco em elementos de interface. "
                    f"Preciso localizar: {query}. "
                    "Inclua bounding boxes normalizadas para os "
                    "elementos relevantes."
                ),
            )

            observation = VisionObservation(
                capture=capture,
                analysis=analysis,
            )

            result = locate_ui_element(
                analysis,
                query,
            )

            # Se o modelo reconheceu o elemento, mas não trouxe bbox
            # confiável, fazemos uma segunda passagem focada somente no alvo.
            if not result.found:
                focused = self.analyzer.locate_target(
                    capture.path,
                    target=query,
                )

                if focused is not None and focused.bbox is not None:
                    result = VisionGroundingResult(
                        query=query,
                        found=True,
                        element=focused,
                        message=(
                            f"Localizei '{focused.label}' na tela "
                            "após uma análise focada."
                        ),
                    )

            return observation, result

        finally:
            if not self.keep_captures:
                capture.path.unlink(missing_ok=True)
