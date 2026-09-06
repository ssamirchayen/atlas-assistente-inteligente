from __future__ import annotations

from pathlib import Path
from atlas.benchmark.core_executors import (
    _configured_model_available,
    _critical_imports,
    _ollama_chat,
    _ollama_health,
)
from atlas.benchmark.models import BenchmarkCase, BenchmarkStatus
from atlas.benchmark.runner import BenchmarkContext


def _context(tmp_path: Path) -> BenchmarkContext:
    return BenchmarkContext(
        project_root=tmp_path,
        scratch_dir=tmp_path,
        run_id="test-run",
        seed=27,
        case_seed=99,
    )


def _case(executor: str, **parameters) -> BenchmarkCase:
    return BenchmarkCase(
        case_id="core.test",
        title="Core test",
        domain="core",
        executor=executor,
        parameters=parameters,
    )


def test_configured_model_available_accepts_latest_alias():
    assert _configured_model_available("atlas", {"atlas:latest"}) is True
    assert _configured_model_available("atlas:8b", {"atlas:latest"}) is False


def test_critical_imports_scores_partial_failure(tmp_path):
    outcome = _critical_imports(
        _case(
            "core.imports",
            modules=["json", "atlas_module_that_does_not_exist_27"],
        ),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.FAIL
    assert outcome.score == 50.0
    assert outcome.metrics["modules_imported"] == 1
    assert outcome.metrics["modules_failed"] == 1


def test_live_ollama_checks_skip_without_live_flag(tmp_path):
    get_called = False
    post_called = False

    def fake_get(*args, **kwargs):
        nonlocal get_called
        get_called = True
        raise AssertionError("GET should not be called")

    def fake_post(*args, **kwargs):
        nonlocal post_called
        post_called = True
        raise AssertionError("POST should not be called")

    health = _ollama_health(
        _case("core.ollama_health"),
        _context(tmp_path),
        live=False,
        timeout_s=1.0,
        http_get=fake_get,
    )
    chat = _ollama_chat(
        _case("core.ollama_chat"),
        _context(tmp_path),
        live=False,
        timeout_s=1.0,
        http_post=fake_post,
    )

    assert health.status is BenchmarkStatus.SKIP
    assert chat.status is BenchmarkStatus.SKIP
    assert get_called is False
    assert post_called is False


def test_live_ollama_health_detects_configured_model(monkeypatch, tmp_path):
    monkeypatch.setattr("atlas.core.config.OLLAMA_MODEL", "atlas")
    monkeypatch.setattr(
        "atlas.core.config.OLLAMA_TAGS_URL",
        "http://localhost:11434/api/tags",
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"models": [{"name": "atlas:latest"}]}

    outcome = _ollama_health(
        _case("core.ollama_health"),
        _context(tmp_path),
        live=True,
        timeout_s=1.0,
        http_get=lambda *args, **kwargs: Response(),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["configured_model_available"] is True


def test_live_ollama_chat_accepts_probe_token(monkeypatch, tmp_path):
    monkeypatch.setattr("atlas.core.config.OLLAMA_MODEL", "atlas")
    monkeypatch.setattr(
        "atlas.core.config.OLLAMA_URL",
        "http://localhost:11434/api/chat",
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": "ATLAS_OK"}}

    outcome = _ollama_chat(
        _case("core.ollama_chat", expected_token="ATLAS_OK"),
        _context(tmp_path),
        live=True,
        timeout_s=1.0,
        http_post=lambda *args, **kwargs: Response(),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["expected_token_matched"] is True
