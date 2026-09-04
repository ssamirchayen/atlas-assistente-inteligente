from __future__ import annotations

from pathlib import Path

from atlas.context.manager import ContextManager
from atlas.planner.intelligent import IntelligentPlanner
from atlas.planner.planner import Planner


ROOT = Path(__file__).resolve().parents[2]


class StubBrain:
    def __init__(self) -> None:
        self.calls = 0

    def respond(self, user_text: str, memory_context: str = "") -> str:
        self.calls += 1
        return "[]"


def test_intelligent_planner_accepts_shared_brain_without_calling_it() -> None:
    brain = StubBrain()

    planner = IntelligentPlanner(ContextManager(), brain=brain)

    assert planner.brain is brain
    assert brain.calls == 0


def test_planner_passes_shared_brain_to_intelligent_layer() -> None:
    brain = StubBrain()

    planner = Planner(ContextManager(), brain=brain)

    assert planner.intelligent.brain is brain
    assert brain.calls == 0


def test_kernel_has_no_eager_brain_or_vision_imports() -> None:
    source = (ROOT / "atlas" / "core" / "kernel.py").read_text(encoding="utf-8")
    import_section = source.split("class AtlasKernel:", maxsplit=1)[0]

    assert "from atlas.brain.ollama import OllamaBrain" not in import_section
    assert "from atlas.vision.service import VisionService" not in import_section
    assert "from atlas.vision.analyzer import OllamaVisionAnalyzer" not in import_section


def test_kernel_registers_brain_and_vision_as_lazy_components() -> None:
    source = (ROOT / "atlas" / "core" / "kernel.py").read_text(encoding="utf-8")

    assert 'self._brain_component = LazyComponent(\n            "brain"' in source
    assert 'self._vision_component = LazyComponent(\n            "vision"' in source
    assert "self.brain = LazyProxy(self._brain_component)" in source
    assert "self.vision = LazyProxy(self._vision_component)" in source


def test_kernel_references_do_not_force_brain_loading() -> None:
    source = (ROOT / "atlas" / "core" / "kernel.py").read_text(encoding="utf-8")

    assert "brain=self.brain" in source
    assert "domain_responder=lambda text: self.brain.respond(text)" in source
    assert "domain_responder=self.brain.respond" not in source


def test_lazy_core_does_not_use_dynamic_import_strings_or_processes() -> None:
    source = (ROOT / "atlas" / "core" / "lazy.py").read_text(encoding="utf-8")

    assert "import_module" not in source
    assert "__import__" not in source
    assert "subprocess" not in source
    assert "process_iter" not in source
