"""Core benchmark executors for Sprint 27 stage 3.

The default cases are local and side-effect free. Live Ollama checks are opt-in
through the benchmark CLI so routine regression runs do not depend on a model
server being available.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from functools import partial
from typing import Any, Callable

import requests

from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner

HttpGet = Callable[..., Any]
HttpPost = Callable[..., Any]


def register_core_executors(
    runner: BenchmarkRunner,
    *,
    live: bool = False,
    ollama_timeout_s: float = 120.0,
    http_get: HttpGet | None = None,
    http_post: HttpPost | None = None,
) -> None:
    """Register local core checks and optional live Ollama probes."""

    timeout = float(ollama_timeout_s)
    if timeout <= 0:
        raise ValueError("ollama_timeout_s must be positive")

    runner.register_executor("core.imports", _critical_imports)
    runner.register_executor("core.text_pipeline", _text_pipeline)
    runner.register_executor("core.lazy_loading", _lazy_loading)
    runner.register_executor("core.runtime_profile", _runtime_profile)
    runner.register_executor("core.model_router", _model_router)
    runner.register_executor(
        "core.ollama_health",
        partial(
            _ollama_health,
            live=live,
            timeout_s=min(timeout, 10.0),
            http_get=http_get or requests.get,
        ),
    )
    runner.register_executor(
        "core.ollama_chat",
        partial(
            _ollama_chat,
            live=live,
            timeout_s=timeout,
            http_post=http_post or requests.post,
        ),
    )


def _critical_imports(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    raw_modules = case.parameters.get("modules", ())
    if not isinstance(raw_modules, (list, tuple)):
        raise TypeError("modules parameter must be a list")

    modules = tuple(str(name).strip() for name in raw_modules if str(name).strip())
    if not modules:
        raise ValueError("modules parameter cannot be empty")

    imported: list[str] = []
    failed: list[str] = []
    for module_name in modules:
        try:
            importlib.import_module(module_name)
            imported.append(module_name)
        except (ImportError, ModuleNotFoundError):
            failed.append(module_name)

    passed = not failed
    score = 100.0 if passed else round(len(imported) / len(modules) * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "modules_total": len(modules),
            "modules_imported": len(imported),
            "modules_failed": len(failed),
        },
        details=(
            "Critical Atlas modules imported successfully."
            if passed
            else "Import failures: " + ", ".join(failed)
        ,),
    )


def _text_pipeline(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    from atlas.utils.text import normalize, remove_wake_word

    raw_samples = case.parameters.get("samples", ())
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("samples parameter must be a non-empty list")

    passed_count = 0
    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        raw_text = str(sample.get("input", ""))
        expected = str(sample.get("expected", ""))
        wake_word = str(sample.get("wake_word", "Atlas"))
        remove_wake = bool(sample.get("remove_wake", False))
        if remove_wake:
            found, output = remove_wake_word(raw_text, wake_word)
            matched = found and output == expected
        else:
            matched = normalize(raw_text) == expected
        if matched:
            passed_count += 1

    total = len(raw_samples)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=(
            BenchmarkStatus.PASS
            if passed_count == total
            else BenchmarkStatus.FAIL
        ),
        score=score,
        metrics={
            "samples_total": total,
            "samples_passed": passed_count,
        },
        details=(f"Text pipeline matched {passed_count}/{total} samples.",),
    )


def _lazy_loading(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case, context
    from atlas.core.lazy import LazyComponent

    created = 0

    def factory() -> dict[str, bool]:
        nonlocal created
        created += 1
        return {"ready": True}

    component = LazyComponent("benchmark.probe", factory)
    unloaded_before = not component.loaded and component.peek() is None
    first = component.get()
    second = component.get()
    snapshot = component.snapshot()
    passed = (
        unloaded_before
        and first is second
        and created == 1
        and snapshot.loaded
        and snapshot.load_attempts == 1
        and snapshot.successful_loads == 1
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "factory_calls": created,
            "load_attempts": snapshot.load_attempts,
            "successful_loads": snapshot.successful_loads,
            "load_duration_ms": round(snapshot.load_duration_ms or 0.0, 3),
        },
        details=("Lazy component loaded once and reused its instance.",),
    )


def _runtime_profile(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    from atlas.core.runtime_profile import (
        RuntimeProfileSelector,
        RuntimeSupportStatus,
        SystemResourceProbe,
    )

    requested = str(case.parameters.get("requested", "auto"))
    snapshot = SystemResourceProbe(project_root=context.project_root).capture()
    decision = RuntimeProfileSelector().select(snapshot, requested)

    if decision.support_status is RuntimeSupportStatus.SUPPORTED:
        score = 100.0
    elif decision.support_status is RuntimeSupportStatus.LIMITED:
        score = 70.0
    else:
        score = 25.0

    metrics: dict[str, float | int | str | bool] = {
        "requested_profile": decision.requested.value,
        "recommended_profile": decision.recommended.value,
        "selected_profile": decision.selected.value,
        "support_status": decision.support_status.value,
        "fallback_applied": decision.fallback_applied,
        "total_memory_gb": round(snapshot.total_memory_gb, 3),
        "available_memory_gb": round(snapshot.available_memory_gb, 3),
        "logical_cpus": snapshot.logical_cpus,
    }
    if snapshot.physical_cpus is not None:
        metrics["physical_cpus"] = snapshot.physical_cpus
    if snapshot.disk_free_gb is not None:
        metrics["disk_free_gb"] = round(snapshot.disk_free_gb, 3)
    if snapshot.gpu_vram_gb is not None:
        metrics["gpu_vram_gb"] = round(snapshot.gpu_vram_gb, 3)

    passed = decision.support_status is not RuntimeSupportStatus.UNSUPPORTED
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics=metrics,
        details=(
            "Runtime profile selected from measured local hardware: "
            f"{decision.selected.value}."
        ,),
    )


def _model_router(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case, context
    from atlas.brain.model_router import (
        ModelCandidate,
        ModelRouter,
        ModelTask,
        ModelTier,
        StaticModelInventory,
    )
    from atlas.core.runtime_profile import (
        HardwareSnapshot,
        RuntimeProfileSelector,
    )

    snapshot = HardwareSnapshot(
        captured_at=datetime.now(UTC),
        total_memory_gb=32.0,
        available_memory_gb=16.0,
        logical_cpus=16,
        physical_cpus=8,
        disk_free_gb=100.0,
        gpu_vram_gb=12.0,
    )
    profile = RuntimeProfileSelector().select(snapshot, "full")
    candidates = (
        ModelCandidate("bench-lite", ModelTier.LITE, 0, 0, 4096),
        ModelCandidate("bench-standard", ModelTier.BALANCED, 0, 0, 8192),
        ModelCandidate("bench-full", ModelTier.LARGE, 0, 0, 16384),
    )
    router = ModelRouter(
        profile=profile,
        candidates=candidates,
        fallback_model="bench-lite",
        inventory=StaticModelInventory(
            {"bench-lite", "bench-standard", "bench-full"}
        ),
    )

    samples = (
        ("Olá Atlas", ModelTask.CHAT, "bench-standard"),
        ("Faça um código Python", ModelTask.CODING, "bench-full"),
        ("Faça uma análise técnica", ModelTask.ANALYSIS, "bench-full"),
        ("Crie um planejador", ModelTask.PLANNING, "bench-full"),
    )
    passed_count = 0
    for text, expected_task, expected_model in samples:
        task = router.classify(text)
        decision = router.route(task)
        if task is expected_task and decision.model_name == expected_model:
            passed_count += 1

    score = round(passed_count / len(samples) * 100.0, 3)
    passed = passed_count == len(samples)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "routing_samples": len(samples),
            "routing_passed": passed_count,
        },
        details=(f"Model Router matched {passed_count}/{len(samples)} cases.",),
    )


def _skip_live(reason: str) -> CaseOutcome:
    return CaseOutcome(
        status=BenchmarkStatus.SKIP,
        score=0.0,
        metrics={"live_check": False},
        details=(reason,),
    )


def _configured_model_available(
    configured: str,
    names: set[str],
) -> bool:
    if configured in names:
        return True
    if ":" not in configured and f"{configured}:latest" in names:
        return True
    return False


def _ollama_health(
    case: BenchmarkCase,
    context: BenchmarkContext,
    *,
    live: bool,
    timeout_s: float,
    http_get: HttpGet,
) -> CaseOutcome:
    del case, context
    if not live:
        return _skip_live("Live Ollama health check disabled; use --live.")

    from atlas.core.config import OLLAMA_MODEL, OLLAMA_TAGS_URL

    try:
        response = http_get(OLLAMA_TAGS_URL, timeout=timeout_s)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, AttributeError, TypeError, ValueError) as exc:
        return CaseOutcome(
            status=BenchmarkStatus.FAIL,
            score=0.0,
            metrics={"ollama_reachable": False, "live_check": True},
            details=(f"Ollama health check failed: {type(exc).__name__}.",),
        )

    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = {
        str(item.get("name") or item.get("model") or "").strip()
        for item in models
        if isinstance(item, dict)
    }
    names.discard("")
    available = _configured_model_available(OLLAMA_MODEL, names)
    score = 100.0 if available else 70.0
    return CaseOutcome(
        status=BenchmarkStatus.PASS if available else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "ollama_reachable": True,
            "configured_model_available": available,
            "local_model_count": len(names),
            "live_check": True,
        },
        details=(
            f"Ollama is reachable; configured model '{OLLAMA_MODEL}' "
            + ("is available." if available else "was not found.")
        ,),
    )


def _ollama_chat(
    case: BenchmarkCase,
    context: BenchmarkContext,
    *,
    live: bool,
    timeout_s: float,
    http_post: HttpPost,
) -> CaseOutcome:
    del context
    if not live:
        return _skip_live("Live Ollama chat check disabled; use --live.")

    from atlas.core.config import OLLAMA_MODEL, OLLAMA_URL

    expected = str(case.parameters.get("expected_token", "ATLAS_OK")).strip()
    prompt = str(
        case.parameters.get(
            "prompt",
            "Responda somente com ATLAS_OK, sem explicações adicionais.",
        )
    )
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    try:
        response = http_post(OLLAMA_URL, json=payload, timeout=timeout_s)
        response.raise_for_status()
        data = response.json()
        answer = str(data["message"]["content"]).strip()
    except (
        requests.RequestException,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return CaseOutcome(
            status=BenchmarkStatus.FAIL,
            score=0.0,
            metrics={"ollama_chat_ok": False, "live_check": True},
            details=(f"Ollama chat failed: {type(exc).__name__}.",),
        )

    normalized = answer.upper().replace(" ", "_")
    matched = bool(expected) and expected.upper().replace(" ", "_") in normalized
    return CaseOutcome(
        status=BenchmarkStatus.PASS if matched else BenchmarkStatus.FAIL,
        score=100.0 if matched else 50.0,
        metrics={
            "ollama_chat_ok": True,
            "expected_token_matched": matched,
            "response_chars": len(answer),
            "live_check": True,
        },
        details=(
            "Ollama returned the expected deterministic probe token."
            if matched
            else "Ollama responded, but the expected probe token was not found."
        ,),
    )
