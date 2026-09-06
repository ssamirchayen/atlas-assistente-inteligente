from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
from types import ModuleType

import pytest

from atlas.benchmark.models import BenchmarkCase, BenchmarkStatus
from atlas.benchmark.runner import BenchmarkContext
from atlas.benchmark.voice_executors import (
    _command_normalizer,
    _dependency_readiness,
    _interruption_detection,
    _neural_synthesis,
    _response_chunking,
    _session_cycle,
)


@pytest.fixture(autouse=True)
def _optional_speech_recognition_stub(monkeypatch):
    """Keep unit tests importable when optional audio deps are absent."""

    if importlib.util.find_spec("speech_recognition") is None:
        monkeypatch.setitem(sys.modules, "speech_recognition", ModuleType("speech_recognition"))


def _context(tmp_path: Path) -> BenchmarkContext:
    return BenchmarkContext(
        project_root=tmp_path,
        scratch_dir=tmp_path,
        run_id="test-run",
        seed=27,
        case_seed=404,
    )


def _case(executor: str, **parameters) -> BenchmarkCase:
    return BenchmarkCase(
        case_id="voice.test",
        title="Voice test",
        domain="voice",
        executor=executor,
        parameters=parameters,
    )


def test_dependency_readiness_scores_missing_dependency(tmp_path):
    available = {"edge_tts", "speech_recognition"}
    outcome = _dependency_readiness(
        _case(
            "voice.dependencies",
            dependencies=["edge_tts", "speech_recognition", "pyaudio"],
        ),
        _context(tmp_path),
        dependency_probe=lambda name: object() if name in available else None,
    )

    assert outcome.status is BenchmarkStatus.FAIL
    assert outcome.metrics["dependencies_available"] == 2
    assert outcome.metrics["dependencies_missing"] == 1


def test_command_normalizer_benchmark_matches_samples(tmp_path):
    outcome = _command_normalizer(
        _case(
            "voice.command_normalizer",
            samples=[
                {"input": "quick no botão", "expected": "clique no botão"},
                {"input": "abre navegador", "expected": "abra navegador"},
                {"input": "desculpa errei abra", "expected": ""},
            ],
        ),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.score == 100.0
    assert outcome.metrics["samples_passed"] == 3


def test_interruption_detection_benchmark_handles_wake_and_followup(tmp_path):
    outcome = _interruption_detection(
        _case(
            "voice.interruption_detection",
            samples=[
                {"input": "Atlas pare", "expected": True},
                {"input": "pare", "expected": False},
                {
                    "input": "pare",
                    "expected": True,
                    "allow_without_wake": True,
                },
                {
                    "input": "Atlas cancele a execução",
                    "expected": True,
                    "cancel_execution": True,
                },
                {"input": "Atlas continue", "expected": False},
            ],
        ),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.score == 100.0
    assert outcome.metrics["positive_recall_pct"] == 100.0
    assert outcome.metrics["negative_specificity_pct"] == 100.0


def test_session_cycle_validates_latency_tracker(tmp_path):
    outcome = _session_cycle(
        _case("voice.session_cycle"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["cycles"] == 2
    assert outcome.metrics["completed"] == 1
    assert outcome.metrics["interrupted"] == 1
    assert outcome.metrics["simulated_total_ms"] == 720.0


def test_neural_synthesis_skips_when_live_is_disabled(tmp_path):
    called = False

    def fake_synthesize(text: str, path: Path, timeout: float) -> None:
        nonlocal called
        called = True

    outcome = _neural_synthesis(
        _case("voice.neural_synthesis"),
        _context(tmp_path),
        live=False,
        timeout_s=1.0,
        synthesize=fake_synthesize,
    )

    assert outcome.status is BenchmarkStatus.SKIP
    assert called is False


def test_neural_synthesis_accepts_generated_audio(tmp_path):
    def fake_synthesize(text: str, path: Path, timeout: float) -> None:
        assert text
        assert timeout == 1.0
        path.write_bytes(b"ID3" + b"atlas" * 20)

    outcome = _neural_synthesis(
        _case("voice.neural_synthesis", text="Atlas teste"),
        _context(tmp_path),
        live=True,
        timeout_s=1.0,
        synthesize=fake_synthesize,
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["synthesis_ok"] is True
    assert outcome.metrics["audio_bytes"] > 0

def test_response_chunking_respects_minimum_supported_limit(tmp_path):
    outcome = _response_chunking(
        _case(
            "voice.response_chunking",
            text=(
                "Atlas está pronto. O benchmark de voz mede blocos de fala. "
                "Esta frase garante conteúdo suficiente para validar a divisão."
            ),
            max_chars=80,
        ),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.score == 100.0
    assert outcome.metrics["chunks"] >= 1
    assert outcome.metrics["max_chunk_chars"] <= 80

