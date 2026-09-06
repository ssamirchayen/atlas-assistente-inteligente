"""Voice benchmark executors for Sprint 27 stage 4.

The automated suite validates the real Atlas voice pipeline without requiring
someone to speak into the microphone. Neural synthesis is opt-in with
``--live`` because Edge TTS depends on network availability.

Acoustic STT accuracy and end-to-end interruption latency are intentionally not
fabricated here; those require controlled audio fixtures or a manual protocol.
"""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner

DependencyProbe = Callable[[str], Any]
SynthesizeFn = Callable[[str, Path, float], None]


def register_voice_executors(
    runner: BenchmarkRunner,
    *,
    live: bool = False,
    tts_timeout_s: float = 30.0,
) -> None:
    """Register deterministic voice checks and optional live neural TTS."""

    timeout = float(tts_timeout_s)
    if timeout <= 0:
        raise ValueError("tts_timeout_s must be positive")

    runner.register_executor("voice.imports", _voice_imports)
    runner.register_executor("voice.dependencies", _dependency_readiness)
    runner.register_executor("voice.configuration", _voice_configuration)
    runner.register_executor("voice.command_normalizer", _command_normalizer)
    runner.register_executor(
        "voice.interruption_detection",
        _interruption_detection,
    )
    runner.register_executor("voice.session_cycle", _session_cycle)
    runner.register_executor("voice.response_chunking", _response_chunking)
    runner.register_executor(
        "voice.neural_synthesis",
        partial(
            _neural_synthesis,
            live=live,
            timeout_s=timeout,
        ),
    )


def _voice_imports(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    raw_modules = case.parameters.get("modules", ())
    if not isinstance(raw_modules, (list, tuple)):
        raise TypeError("modules parameter must be a list")

    modules = tuple(str(item).strip() for item in raw_modules if str(item).strip())
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

    score = round(len(imported) / len(modules) * 100.0, 3)
    passed = not failed
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "modules_total": len(modules),
            "modules_imported": len(imported),
            "modules_failed": len(failed),
        },
        details=(
            "Voice modules imported successfully."
            if passed
            else "Voice import failures: " + ", ".join(failed)
        ,),
    )


def _dependency_readiness(
    case: BenchmarkCase,
    context: BenchmarkContext,
    *,
    dependency_probe: DependencyProbe = importlib.util.find_spec,
) -> CaseOutcome:
    del context
    raw_dependencies = case.parameters.get(
        "dependencies",
        ["edge_tts", "speech_recognition", "pyaudio"],
    )
    if not isinstance(raw_dependencies, (list, tuple)) or not raw_dependencies:
        raise ValueError("dependencies parameter must be a non-empty list")

    dependencies = tuple(
        str(item).strip() for item in raw_dependencies if str(item).strip()
    )
    available: list[str] = []
    missing: list[str] = []
    for name in dependencies:
        try:
            found = dependency_probe(name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            found = False
        (available if found else missing).append(name)

    score = round(len(available) / len(dependencies) * 100.0, 3)
    passed = not missing
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "dependencies_total": len(dependencies),
            "dependencies_available": len(available),
            "dependencies_missing": len(missing),
        },
        details=(
            "Voice runtime dependencies are available."
            if passed
            else "Missing voice dependencies: " + ", ".join(missing)
        ,),
    )


def _voice_configuration(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    from atlas.core.config import (
        MIC_ENABLED,
        TTS_PROVIDER,
        TTS_VOICE,
        VOICE_ENABLED,
        VOICE_PROFILE,
        WAKE_WORD_ENABLED,
    )
    from atlas.voice.profile import resolve_voice_profile

    expected_provider = str(
        case.parameters.get("expected_provider", "edge")
    ).strip().lower()
    expected_voice = str(
        case.parameters.get("expected_voice", "pt-BR-AntonioNeural")
    ).strip()
    allowed_profiles = {
        str(item).strip().lower()
        for item in case.parameters.get(
            "allowed_profiles",
            ["fast", "balanced", "accurate"],
        )
    }

    profile = resolve_voice_profile(VOICE_PROFILE)
    checks = {
        "voice_enabled": bool(VOICE_ENABLED),
        "microphone_enabled": bool(MIC_ENABLED),
        "wake_word_enabled": bool(WAKE_WORD_ENABLED),
        "provider_expected": TTS_PROVIDER == expected_provider,
        "voice_expected": TTS_VOICE == expected_voice,
        "profile_supported": profile.name.lower() in allowed_profiles,
    }
    passed_count = sum(checks.values())
    total = len(checks)
    passed = passed_count == total
    score = round(passed_count / total * 100.0, 3)

    metrics: dict[str, float | int | str | bool] = {
        **checks,
        "tts_provider": TTS_PROVIDER,
        "tts_voice": TTS_VOICE,
        "voice_profile": profile.name,
        "pause_threshold_s": profile.pause_threshold,
        "phrase_threshold_s": profile.phrase_threshold,
    }
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics=metrics,
        details=(
            f"Voice configuration matched {passed_count}/{total} requirements.",
        ),
    )


def _command_normalizer(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    from atlas.voice.command_normalizer import normalize_voice_command

    raw_samples = case.parameters.get("samples", ())
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("samples parameter must be a non-empty list")

    passed_count = 0
    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        value = normalize_voice_command(str(sample.get("input", "")))
        if value == str(sample.get("expected", "")):
            passed_count += 1

    total = len(raw_samples)
    score = round(passed_count / total * 100.0, 3)
    passed = passed_count == total
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "samples_total": total,
            "samples_passed": passed_count,
            "normalization_accuracy_pct": score,
        },
        details=(
            f"Voice command normalization matched {passed_count}/{total} samples.",
        ),
    )


def _interruption_detection(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    from atlas.voice.interruption import detect_voice_interruption

    raw_samples = case.parameters.get("samples", ())
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("samples parameter must be a non-empty list")

    passed_count = 0
    positives = 0
    true_positives = 0
    negatives = 0
    true_negatives = 0

    for sample in raw_samples:
        if not isinstance(sample, dict):
            continue
        expected = bool(sample.get("expected", False))
        allow_without_wake = bool(sample.get("allow_without_wake", False))
        intent = detect_voice_interruption(
            str(sample.get("input", "")),
            str(sample.get("wake_word", "Atlas")),
            allow_without_wake=allow_without_wake,
        )
        detected = intent is not None
        matched = detected is expected

        if expected:
            positives += 1
            true_positives += int(detected)
        else:
            negatives += 1
            true_negatives += int(not detected)

        expected_cancel = sample.get("cancel_execution")
        if matched and expected_cancel is not None and intent is not None:
            matched = intent.cancel_execution is bool(expected_cancel)

        passed_count += int(matched)

    total = len(raw_samples)
    score = round(passed_count / total * 100.0, 3)
    passed = passed_count == total
    sensitivity = (
        round(true_positives / positives * 100.0, 3) if positives else 100.0
    )
    specificity = (
        round(true_negatives / negatives * 100.0, 3) if negatives else 100.0
    )
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            "samples_total": total,
            "samples_passed": passed_count,
            "intent_accuracy_pct": score,
            "positive_recall_pct": sensitivity,
            "negative_specificity_pct": specificity,
        },
        details=(
            f"Interruption intent detection matched {passed_count}/{total} samples.",
        ),
    )


def _session_cycle(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case, context
    from atlas.voice.latency import VoiceCycleOutcome, VoiceLatencyTracker
    from atlas.voice.session import VoiceSession

    tick = [0.0]

    def clock() -> float:
        return tick[0]

    session = VoiceSession()
    tracker = VoiceLatencyTracker(session, history_limit=8, clock=clock)

    session.start_listening()
    tick[0] = 0.120
    session.start_processing("Atlas teste")
    tick[0] = 0.370
    session.start_speaking()
    tick[0] = 0.720
    session.complete()

    first = tracker.latest()

    tick[0] = 1.000
    session.start_listening()
    tick[0] = 1.080
    session.start_processing("Atlas pare")
    tick[0] = 1.150
    session.start_speaking()
    tick[0] = 1.210
    session.interrupt("benchmark")

    second = tracker.latest()
    summary = tracker.summary()
    tracker.close()

    passed = bool(
        first is not None
        and first.outcome is VoiceCycleOutcome.COMPLETED
        and first.recognized
        and first.listening_ms == 120.0
        and first.processing_ms == 250.0
        and first.speaking_ms == 350.0
        and first.total_ms == 720.0
        and second is not None
        and second.outcome is VoiceCycleOutcome.INTERRUPTED
        and summary["cycles"] == 2
        and summary["completed"] == 1
        and summary["interrupted"] == 1
    )

    metrics: dict[str, float | int | str | bool] = {
        "cycles": int(summary["cycles"] or 0),
        "completed": int(summary["completed"] or 0),
        "interrupted": int(summary["interrupted"] or 0),
    }
    if first is not None:
        metrics.update(
            {
                "simulated_listening_ms": first.listening_ms,
                "simulated_processing_ms": first.processing_ms,
                "simulated_speaking_ms": first.speaking_ms,
                "simulated_total_ms": first.total_ms,
            }
        )

    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=(
            "VoiceSession transitions and latency telemetry are consistent.",
        ),
    )


def _response_chunking(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del context
    from atlas.voice.response import split_for_speech

    text = str(
        case.parameters.get(
            "text",
            "Atlas está pronto. O benchmark de voz mede blocos de fala. "
            "Esta frase garante que existe conteúdo suficiente para divisão.",
        )
    ).strip()
    max_chars = int(case.parameters.get("max_chars", 80))
    if max_chars < 80:
        raise ValueError("max_chars must be at least 80")

    chunks = split_for_speech(text, max_chars=max_chars)
    non_empty = bool(chunks) and all(str(chunk).strip() for chunk in chunks)
    max_observed = max((len(chunk) for chunk in chunks), default=0)
    reconstructed_chars = sum(len(chunk) for chunk in chunks)
    passed = non_empty and reconstructed_chars > 0

    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "chunks": len(chunks),
            "max_chunk_chars": max_observed,
            "source_chars": len(text),
        },
        details=("TTS response chunking produced non-empty speech blocks.",),
    )


def _neural_synthesis(
    case: BenchmarkCase,
    context: BenchmarkContext,
    *,
    live: bool,
    timeout_s: float,
    synthesize: SynthesizeFn | None = None,
) -> CaseOutcome:
    if not live:
        return CaseOutcome(
            status=BenchmarkStatus.SKIP,
            score=0.0,
            metrics={"live_check": False},
            details=("Live neural synthesis disabled; use --live.",),
        )

    text = str(
        case.parameters.get(
            "text",
            "Atlas benchmark de voz neural concluído.",
        )
    ).strip()
    if not text:
        raise ValueError("neural synthesis text cannot be empty")

    output = context.scratch_dir / "atlas_voice_benchmark.mp3"

    try:
        if synthesize is None:
            from atlas.core.config import (
                TTS_PITCH,
                TTS_RATE,
                TTS_VOICE,
                TTS_VOLUME,
            )
            from atlas.voice.tts import EdgeTTSProvider

            provider = EdgeTTSProvider(
                voice=TTS_VOICE or "pt-BR-AntonioNeural",
                rate=TTS_RATE or "+0%",
                volume=TTS_VOLUME or "+0%",
                pitch=TTS_PITCH or "+0Hz",
            )
            provider.synthesize(text, output, timeout=timeout_s)
        else:
            synthesize(text, output, timeout_s)
    except Exception as exc:
        return CaseOutcome(
            status=BenchmarkStatus.FAIL,
            score=0.0,
            metrics={"live_check": True, "synthesis_ok": False},
            details=(f"Neural synthesis failed: {type(exc).__name__}.",),
        )

    size_bytes = output.stat().st_size if output.exists() else 0
    passed = size_bytes > 0
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={
            "live_check": True,
            "synthesis_ok": passed,
            "audio_bytes": size_bytes,
            "text_chars": len(text),
        },
        details=(
            "Edge neural TTS generated an audio artifact."
            if passed
            else "Edge neural TTS returned no audio artifact."
        ,),
    )
