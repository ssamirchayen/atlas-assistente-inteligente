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
    def __init__(self, *, apply_state: bool = True) -> None:
        self.checked = False
        self.apply_state = apply_state
        self.requests: list[bool] = []

    def inspect_visible_interactive_elements(self):
        return [
            {
                "dom_index": 0,
                "tag": "input",
                "role": "checkbox",
                "type": "checkbox",
                "name": "novidades",
                "aria_label": "Receber novidades",
                "placeholder": "",
                "title": "",
                "labels": "Receber novidades",
                "text": "",
                "left": 10,
                "top": 10,
                "right": 40,
                "bottom": 40,
            }
        ]

    def get_structural_context_token(self) -> str:
        return "dom:test"

    def inspect_interaction_state(self, *args, **kwargs):
        return {
            "target_index": 0,
            "target": {
                "tag": "input",
                "role": "checkbox",
                "type": "checkbox",
                "disabled": False,
                "checked": self.checked,
            },
        }

    def set_interactive_control_state(self, index, desired, **kwargs):
        self.requests.append(desired)
        if self.apply_state or len(self.requests) > 1:
            self.checked = desired
        return True


def _service(tmp_path: Path, browser: _Browser) -> AtlasGuiService:
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
    return service


def test_executes_and_verifies_checkbox_state(tmp_path: Path) -> None:
    browser = _Browser()
    result = _service(tmp_path, browser).execute(
        "marque a caixa de seleção receber novidades"
    )

    assert result.success is True
    assert result.action_count == 1
    assert browser.checked is True
    assert result.reason_code == "control_checked_confirmed"


def test_rolls_back_when_post_state_is_not_confirmed(tmp_path: Path) -> None:
    browser = _Browser(apply_state=False)
    result = _service(tmp_path, browser).execute(
        "marque a caixa de seleção receber novidades"
    )

    assert result.success is False
    assert result.action_count == 2
    assert browser.requests == [True, False]
    assert result.reason_code == "vision_control_not_verified_rolled_back"

