from atlas.core.config import (
    VISION_CAPTURE_DIR,
    VISION_KEEP_CAPTURES,
    VISION_MODEL,
)
from atlas.vision.analyzer import (
    OllamaVisionAnalyzer,
    VisionAnalysisError,
)
from atlas.vision.capture import (
    ScreenCaptureError,
    ScreenCaptureService,
)
from atlas.vision.formatter import format_analysis_for_user
from atlas.vision.service import VisionService


def main() -> None:
    print(f"Atlas Vision — modelo: {VISION_MODEL}")

    service = VisionService(
        ScreenCaptureService(VISION_CAPTURE_DIR),
        OllamaVisionAnalyzer(),
        keep_captures=VISION_KEEP_CAPTURES,
    )

    try:
        observation = service.observe_screen(
            "O que você está vendo na minha tela? "
            "Se houver erro visível, destaque-o."
        )
    except (ScreenCaptureError, VisionAnalysisError) as error:
        print(f"[VISION ERRO] {error}")
        print(
            "Se o modelo ainda não estiver instalado, execute: "
            f"ollama pull {VISION_MODEL}"
        )
        raise SystemExit(1) from error

    print()
    print("Atlas:")
    print(format_analysis_for_user(observation.analysis))
    print()
    print(f"Confiança: {observation.analysis.confidence:.0%}")

    if observation.analysis.applications:
        print(
            "Aplicações: "
            + ", ".join(observation.analysis.applications)
        )

    if observation.analysis.visible_text:
        print("Textos relevantes:")
        for text in observation.analysis.visible_text[:8]:
            print(f"- {text}")


if __name__ == "__main__":
    main()
