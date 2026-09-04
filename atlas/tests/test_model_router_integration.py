from __future__ import annotations

from typing import Any

from atlas.brain.model_router import ModelRouteDecision, ModelTask, ModelTier
from atlas.brain.ollama import OllamaBrain
from atlas.context.manager import ContextManager
from atlas.core.runtime_profile import RuntimeProfile


class FakeRouter:
    def __init__(self) -> None:
        self.classified: list[str] = []
        self.routed: list[ModelTask] = []

    def classify(self, text: str) -> ModelTask:
        self.classified.append(text)
        return ModelTask.CODING

    def route(self, task: ModelTask) -> ModelRouteDecision:
        self.routed.append(task)
        return ModelRouteDecision(
            task=task,
            profile=RuntimeProfile.STANDARD,
            target_tier=ModelTier.BALANCED,
            selected_tier=ModelTier.BALANCED,
            model_name="qwen3:8b",
            context_limit=8192,
            fallback_applied=False,
            reason_codes=("best_supported_candidate",),
        )


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, dict[str, str]]:
        return {"message": {"content": "Resposta roteada."}}


def test_brain_uses_router_model_and_context(
    monkeypatch,
    tmp_path,
) -> None:
    router = FakeRouter()
    context = ContextManager()
    captured: dict[str, Any] = {}

    def post(_url: str, *, json: dict[str, Any], timeout: int) -> FakeResponse:
        captured.update(json)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("atlas.brain.ollama.requests.post", post)
    brain = OllamaBrain(context, model_router=router)  # type: ignore[arg-type]

    assert brain.respond("Corrija este código Python") == "Resposta roteada."
    assert captured["model"] == "qwen3:8b"
    assert captured["options"] == {"num_ctx": 8192}
    assert router.routed == [ModelTask.CODING]
    assert brain.last_model_decision is not None


def test_brain_without_router_preserves_legacy_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def post(_url: str, *, json: dict[str, Any], timeout: int) -> FakeResponse:
        captured.update(json)
        return FakeResponse()

    monkeypatch.setattr("atlas.brain.ollama.requests.post", post)
    brain = OllamaBrain(ContextManager())
    brain.respond("Olá")

    assert "options" not in captured
    assert brain.last_model_decision is None


def test_kernel_builds_router_only_inside_lazy_brain() -> None:
    source = open("atlas/core/kernel.py", encoding="utf-8").read()
    import_section = source.split("class AtlasKernel:", maxsplit=1)[0]
    factory = source.split("def _build_brain", maxsplit=1)[1]

    assert "model_router" not in import_section
    assert "create_default_model_router" in factory
    assert "self.runtime_profile" in factory
    assert "self.resource_manager" in factory


def test_router_decision_never_contains_user_prompt() -> None:
    decision = FakeRouter().route(ModelTask.CHAT)
    assert not hasattr(decision, "prompt")
    assert not hasattr(decision, "user_text")
