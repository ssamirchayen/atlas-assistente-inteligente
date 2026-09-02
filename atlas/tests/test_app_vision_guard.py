from types import SimpleNamespace

from atlas.core.app import AtlasApp
from atlas.vision.models import (
    ScreenCapture,
    VisionAnalysis,
    VisionObservation,
)


class FakeSpeech:
    def __init__(self) -> None:
        self.messages = []

    def say(self, message: str) -> None:
        self.messages.append(message)


class FakeVision:
    def observe_screen(self, question: str) -> VisionObservation:
        assert "tela" in question.lower() or "vendo" in question.lower()
        return VisionObservation(
            capture=ScreenCapture(
                path=__import__("pathlib").Path("screen.png"),
                width=1920,
                height=1080,
                captured_at=__import__("datetime").datetime.now(),
            ),
            analysis=VisionAnalysis(
                summary="Vejo um terminal aberto.",
                confidence=0.95,
                model="fake",
            ),
        )


def test_app_handles_vision_before_other_layers() -> None:
    app = AtlasApp.__new__(AtlasApp)
    speech = FakeSpeech()
    app.kernel = SimpleNamespace(
        vision=FakeVision(),
        speech=speech,
    )
    app.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    turns = []
    app._add_turn = lambda command, answer: turns.append(
        (command, answer)
    )

    handled = app._process_vision(
        "o que você está vendo na tela?"
    )

    assert handled is True
    assert speech.messages == ["Vejo um terminal aberto."]
    assert turns
