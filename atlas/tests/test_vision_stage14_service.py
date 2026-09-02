from dataclasses import dataclass
from pathlib import Path

from atlas.gui.service import AtlasGuiService
from atlas.vision.audit import VisionAuditTrail
from atlas.vision.final_action import VisionConfirmationStore


@dataclass
class _Capture:
    path: Path
    width: int = 1000
    height: int = 800


class _CaptureService:
    def __init__(self, path: Path) -> None:
        self.path = path

    def capture_primary_screen(self) -> _Capture:
        self.path.write_bytes(b"screen")
        return _Capture(self.path)


class _Context:
    def __init__(self) -> None:
        self.turns: list[tuple[str, str]] = []

    def add_turn(self, command: str, response: str) -> None:
        self.turns.append((command, response))


class _Browser:
    def __init__(self) -> None:
        self.context_token = "dom:form"
        self.activated = False

    def inspect_visible_interactive_elements(self):
        return [
            {
                "dom_index": 2,
                "tag": "button",
                "role": "button",
                "type": "submit",
                "name": "send",
                "aria_label": "Enviar",
                "placeholder": "",
                "title": "",
                "labels": "",
                "text": "Enviar",
                "left": 100,
                "top": 100,
                "right": 240,
                "bottom": 150,
            }
        ]

    def get_structural_context_token(self) -> str:
        return self.context_token

    def inspect_interaction_state(self, *args, **kwargs):
        return {
            "url": (
                "http://atlas.local/sucesso"
                if self.activated
                else "http://atlas.local/form"
            ),
            "title": "Laboratório",
            "target_index": 2,
            "target": {
                "tag": "button",
                "role": "button",
                "type": "submit",
                "name": "send",
                "aria_label": "enviar",
                "text": "enviar",
                "disabled": False,
                "exists": True,
            },
        }

    def activate_final_control(self, *args, **kwargs) -> bool:
        self.activated = True
        return True


def _service(tmp_path: Path) -> tuple[AtlasGuiService, _Browser]:
    browser = _Browser()
    service = object.__new__(AtlasGuiService)
    service.kernel = type(
        "Kernel",
        (),
        {
            "vision": type(
                "Vision",
                (),
                {
                    "capture_service": _CaptureService(tmp_path / "screen.png"),
                    "keep_captures": False,
                },
            )(),
            "automation": type("Automation", (), {"browser": browser})(),
            "context": _Context(),
        },
    )()
    service.vision_confirmation = VisionConfirmationStore(
        token_factory=lambda: "TOKEN123"
    )
    service.vision_audit = VisionAuditTrail()
    return service, browser


def test_final_action_requires_separate_single_use_confirmation(tmp_path) -> None:
    service, browser = _service(tmp_path)

    prepared = service.execute("enviar o formulário")
    confirmed = service.execute("CONFIRMAR VISÃO TOKEN123")
    repeated = service.execute("CONFIRMAR VISÃO TOKEN123")

    assert prepared.requires_confirmation is True
    assert prepared.action_count == 0
    assert browser.activated is True
    assert confirmed.success is True
    assert confirmed.action_count == 1
    assert confirmed.reason_code == "navigation_changed"
    assert repeated.success is False
    assert repeated.reason_code == "vision_final_confirmation_invalid"


def test_confirmation_is_cancelled_if_page_context_changes(tmp_path) -> None:
    service, browser = _service(tmp_path)
    service.execute("enviar o formulário")
    browser.context_token = "dom:other-tab"

    result = service.execute("CONFIRMAR VISÃO TOKEN123")

    assert result.success is False
    assert result.reason_code == "vision_final_context_changed"
    assert browser.activated is False

