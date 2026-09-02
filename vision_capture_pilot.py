from atlas.core.config import VISION_CAPTURE_DIR
from atlas.vision.capture import ScreenCaptureService


def main() -> None:
    service = ScreenCaptureService(VISION_CAPTURE_DIR)
    capture = service.capture_primary_screen()

    print("Atlas Vision — captura concluída")
    print(f"Arquivo: {capture.path}")
    print(f"Resolução: {capture.width}x{capture.height}")


if __name__ == "__main__":
    main()
