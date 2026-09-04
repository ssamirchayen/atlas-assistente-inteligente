from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from atlas.brain.model_router import (
    ModelCandidate,
    ModelRouter,
    ModelTask,
    ModelTier,
    OllamaModelInventory,
    StaticModelInventory,
)
from atlas.core.resource_manager import ResourcePressure
from atlas.core.runtime_profile import HardwareSnapshot, RuntimeProfileSelector


def profile(
    requested: str,
    *,
    total: float = 32,
    available: float = 16,
    vram: float | None = 12,
):
    snapshot = HardwareSnapshot(
        captured_at=datetime.now(timezone.utc),
        total_memory_gb=total,
        available_memory_gb=available,
        logical_cpus=16,
        physical_cpus=8,
        disk_free_gb=100,
        gpu_vram_gb=vram,
    )
    return RuntimeProfileSelector().select(snapshot, requested)


def candidates() -> tuple[ModelCandidate, ...]:
    return (
        ModelCandidate("atlas-lite", ModelTier.LITE, 7, 1, 4096),
        ModelCandidate("atlas-standard", ModelTier.BALANCED, 14, 2.5, 8192),
        ModelCandidate("atlas-full", ModelTier.LARGE, 28, 6, 16384, 8),
    )


def router(
    requested: str = "full",
    *,
    total: float = 32,
    available: float = 16,
    vram: float | None = 12,
    models: set[str] | None = None,
    pressure: ResourcePressure = ResourcePressure.NORMAL,
) -> ModelRouter:
    inventory = StaticModelInventory(
        models
        if models is not None
        else {"atlas-lite", "atlas-standard", "atlas-full"}
    )
    status = SimpleNamespace(
        status=lambda: SimpleNamespace(pressure=pressure)
    )
    return ModelRouter(
        profile=profile(
            requested,
            total=total,
            available=available,
            vram=vram,
        ),
        candidates=candidates(),
        fallback_model="atlas-lite",
        inventory=inventory,
        resource_status=status,
    )


@pytest.mark.parametrize(
    ("requested", "task", "expected"),
    [
        ("lite", ModelTask.ANALYSIS, "atlas-lite"),
        ("standard", ModelTask.CHAT, "atlas-standard"),
        ("standard", ModelTask.CODING, "atlas-standard"),
        ("full", ModelTask.CHAT, "atlas-standard"),
        ("full", ModelTask.PLANNING, "atlas-full"),
        ("full", ModelTask.CODING, "atlas-full"),
        ("full", ModelTask.ANALYSIS, "atlas-full"),
    ],
)
def test_routes_by_profile_and_task(
    requested: str,
    task: ModelTask,
    expected: str,
) -> None:
    assert router(requested).route(task).model_name == expected


def test_warning_pressure_reduces_large_to_balanced() -> None:
    decision = router(pressure=ResourcePressure.WARNING).route(ModelTask.CODING)
    assert decision.model_name == "atlas-standard"
    assert "warning_pressure_reduced_tier" in decision.reason_codes


def test_critical_pressure_reduces_to_lite() -> None:
    decision = router(pressure=ResourcePressure.CRITICAL).route(ModelTask.ANALYSIS)
    assert decision.model_name == "atlas-lite"
    assert "critical_pressure_reduced_tier" in decision.reason_codes


def test_unavailable_inventory_uses_configured_fallback() -> None:
    model_router = ModelRouter(
        profile=profile("standard"),
        candidates=candidates(),
        fallback_model="atlas-lite",
        inventory=StaticModelInventory(None),
    )
    decision = model_router.route(ModelTask.CHAT)
    assert decision.model_name == "atlas-lite"
    assert decision.fallback_applied is True
    assert "inventory_unavailable" in decision.reason_codes


def test_empty_inventory_uses_configured_fallback() -> None:
    decision = router(models=set()).route(ModelTask.CHAT)
    assert decision.model_name == "atlas-lite"
    assert "configured_fallback_selected" in decision.reason_codes


def test_missing_large_model_falls_back_to_balanced() -> None:
    decision = router(models={"atlas-lite", "atlas-standard"}).route(
        ModelTask.CODING
    )
    assert decision.model_name == "atlas-standard"
    assert decision.fallback_applied is True


def test_available_latest_alias_is_recognized() -> None:
    decision = router(models={"atlas-lite:latest", "atlas-standard:latest"}).route(
        ModelTask.CHAT
    )
    assert decision.model_name == "atlas-standard"


def test_available_ram_blocks_heavier_candidate() -> None:
    decision = router(
        "standard",
        total=16,
        available=1.5,
    ).route(ModelTask.CHAT)
    assert decision.model_name == "atlas-lite"


def test_vram_blocks_large_candidate_when_metric_is_known() -> None:
    decision = router(vram=4).route(ModelTask.CODING)
    assert decision.model_name == "atlas-standard"


def test_unknown_vram_does_not_invent_a_failure() -> None:
    decision = router(vram=None).route(ModelTask.CODING)
    assert decision.model_name == "atlas-full"


def test_profile_context_budget_caps_candidate() -> None:
    decision = router("standard").route(ModelTask.CHAT)
    assert decision.context_limit == 8192


def test_resource_status_failure_is_visible_but_non_blocking() -> None:
    status = SimpleNamespace(
        status=lambda: (_ for _ in ()).throw(RuntimeError("indisponível"))
    )
    model_router = ModelRouter(
        profile=profile("full"),
        candidates=candidates(),
        fallback_model="atlas-lite",
        inventory=StaticModelInventory(
            {"atlas-lite", "atlas-standard", "atlas-full"}
        ),
        resource_status=status,
    )
    decision = model_router.route(ModelTask.CODING)
    assert decision.model_name == "atlas-full"
    assert "resource_status_unavailable" in decision.reason_codes


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Olá, tudo bem?", ModelTask.CHAT),
        ("Você é o planejador e deve retornar lista JSON", ModelTask.PLANNING),
        ("Corrija este código Python", ModelTask.CODING),
        ("Faça uma análise comparativa", ModelTask.ANALYSIS),
    ],
)
def test_classification_does_not_store_text(text: str, expected: ModelTask) -> None:
    model_router = router()
    assert model_router.classify(text) is expected
    decision = model_router.route(expected)
    assert text not in repr(decision)


def test_last_decision_is_observable() -> None:
    model_router = router()
    decision = model_router.route(ModelTask.CHAT)
    assert model_router.last_decision is decision
    assert decision.public_summary()["model_name"] == "atlas-standard"


def test_invalid_task_is_rejected() -> None:
    with pytest.raises(ValueError, match="Tarefa"):
        router().route("desconhecida")


@pytest.mark.parametrize("name", ["", " modelo", "modelo com espaço", "x" * 129])
def test_invalid_model_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="modelo inválido"):
        ModelCandidate(name, ModelTier.LITE, 0, 0, 4096)


def test_duplicate_candidates_are_deterministic() -> None:
    duplicated = candidates() + (candidates()[1],)
    model_router = ModelRouter(
        profile=profile("standard"),
        candidates=duplicated,
        fallback_model="atlas-lite",
        inventory=StaticModelInventory({"atlas-lite", "atlas-standard"}),
    )
    assert model_router.route(ModelTask.CHAT).model_name == "atlas-standard"


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_ollama_inventory_reads_names_and_caches_once() -> None:
    calls: list[str] = []

    def get(url: str, *, timeout: float) -> FakeResponse:
        calls.append(f"{url}:{timeout}")
        return FakeResponse(
            {"models": [{"name": "atlas:latest"}, {"model": "qwen3:8b"}]}
        )

    inventory = OllamaModelInventory(
        "http://localhost:11434/api/tags",
        timeout=1.5,
        getter=get,
    )
    assert inventory.available_models() == {"atlas:latest", "qwen3:8b"}
    assert inventory.available_models() == {"atlas:latest", "qwen3:8b"}
    assert len(calls) == 1


def test_ollama_inventory_failure_is_cached_without_error_details() -> None:
    calls = 0

    def get(_url: str, *, timeout: float) -> FakeResponse:
        nonlocal calls
        calls += 1
        raise requests.ConnectionError("token-ou-detalhe-sensível")

    inventory = OllamaModelInventory(
        "http://localhost:11434/api/tags",
        getter=get,
    )
    assert inventory.available_models() is None
    assert inventory.available_models() is None
    assert calls == 1
    assert "sensível" not in repr(inventory.available_models())

