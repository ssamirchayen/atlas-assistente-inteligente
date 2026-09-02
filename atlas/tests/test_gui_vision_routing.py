from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from atlas.gui.service import AtlasGuiService
from atlas.vision.models import (
    ScreenCapture,
    VisionAnalysis,
    VisionObservation,
)


class FakeVision:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def observe_screen(self, question: str) -> VisionObservation:
        self.questions.append(question)
        return VisionObservation(
            capture=ScreenCapture(
                path=Path("screen.png"),
                width=1920,
                height=1080,
                captured_at=datetime.now(),
            ),
            analysis=VisionAnalysis(
                summary="Vejo o PowerShell aberto.",
                confidence=0.95,
                model="fake",
            ),
        )


class FakeController:
    def __init__(self) -> None:
        self.called = False

    def execute(self, command: str):
        self.called = True
        return (), ()


class FakeRouter:
    @staticmethod
    def route_priority(command: str):
        return SimpleNamespace(handled=False, message="")

    @staticmethod
    def route(command: str):
        return SimpleNamespace(handled=False, message="")


class FakeContext:
    def __init__(self) -> None:
        self.turns = []

    def add_turn(self, command: str, answer: str) -> None:
        self.turns.append((command, answer))

    @staticmethod
    def get_recent_history() -> str:
        return ""


class FakeSession:
    @staticmethod
    def save_last_command(command: str) -> None:
        return None


def make_service():
    vision = FakeVision()
    controller = FakeController()
    context = FakeContext()

    kernel = SimpleNamespace(
        vision=vision,
        router=FakeRouter(),
        context=context,
        session=FakeSession(),
        memory=SimpleNamespace(context=lambda command: ""),
        brain=SimpleNamespace(respond=lambda command, context: "brain"),
        scheduler=SimpleNamespace(),
    )

    service = AtlasGuiService(
        kernel=kernel,
        controller=controller,
        enable_scheduler=False,
    )
    return service, vision, controller, context


def test_gui_routes_vision_before_controller() -> None:
    service, vision, controller, context = make_service()

    result = service.execute("o que voce esta vendo")

    assert result.source == "vision"
    assert result.message == "Vejo o PowerShell aberto."
    assert result.success is True
    assert vision.questions == ["o que voce esta vendo"]
    assert controller.called is False
    assert context.turns


def test_gui_does_not_route_visual_action_as_read_only_vision() -> None:
    service, vision, controller, _ = make_service()

    service.execute("clique no botao que esta na tela")

    assert vision.questions == []
    assert controller.called is True
