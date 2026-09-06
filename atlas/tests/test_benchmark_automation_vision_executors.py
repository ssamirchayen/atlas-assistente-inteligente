from __future__ import annotations

from pathlib import Path

from atlas.benchmark.automation_vision_executors import (
    _automation_engine_contract,
    _automation_file_sandbox,
    _direct_url_intent,
    _domain_generators,
    _is_loopback_http_endpoint,
    _live_analysis,
    _live_capture,
    _post_action_verification,
    _structured_intents,
    _synthetic_capture,
    _synthetic_grounding,
    _vision_intent_routes,
)
from atlas.benchmark.models import BenchmarkCase, BenchmarkStatus
from atlas.benchmark.runner import BenchmarkContext
from atlas.planner.results import ExecutionResult


def _context(tmp_path: Path) -> BenchmarkContext:
    return BenchmarkContext(
        project_root=tmp_path,
        scratch_dir=tmp_path,
        run_id="test-run",
        seed=27,
        case_seed=505,
    )


def _case(executor: str, **parameters) -> BenchmarkCase:
    return BenchmarkCase(
        case_id="automation_vision.test",
        title="Automation Vision test",
        domain="automation_vision",
        executor=executor,
        parameters=parameters,
    )


class _ContractEngine:
    def execute(self, action):
        if action.type == "benchmark.unknown":
            return ExecutionResult.fail(
                action.type,
                "unknown",
                error_code="unknown_action",
            )
        if action.type == "file.create_file":
            return ExecutionResult.fail(
                action.type,
                "missing",
                error_code="missing_parameter",
            )
        return ExecutionResult.fail(
            action.type,
            "invalid",
            error_code="invalid_parameter",
        )

    def close(self) -> None:
        return None


def test_direct_url_intent_benchmark_matches_positive_and_negative_samples(tmp_path):
    outcome = _direct_url_intent(
        _case(
            "automation.url_intent",
            samples=[
                {
                    "input": "abra https://example.com/path?q=1",
                    "expected_url": "https://example.com/path?q=1",
                },
                {
                    "input": "abra https://example.com e depois clique",
                    "expected_url": None,
                },
            ],
        ),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.score == 100.0
    assert outcome.metrics["samples_passed"] == 2


def test_domain_generators_benchmark_is_deterministic(tmp_path):
    outcome = _domain_generators(
        _case("automation.domain_generators"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["helpdesk"] is True
    assert outcome.metrics["sales"] is True
    assert outcome.metrics["hr"] is True


def test_automation_engine_contract_scores_expected_errors(tmp_path):
    outcome = _automation_engine_contract(
        _case("automation.engine_contract"),
        _context(tmp_path),
        live=True,
        engine_factory=_ContractEngine,
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["unknown_action"] is True
    assert outcome.metrics["missing_parameter"] is True
    assert outcome.metrics["invalid_parameter"] is True


def test_automation_file_sandbox_stays_inside_scratch(tmp_path):
    outcome = _automation_file_sandbox(
        _case("automation.file_sandbox"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["sandbox_only"] is True
    assert outcome.metrics["checks_passed"] == outcome.metrics["checks_total"]


def test_vision_intent_routes_classifies_commands(tmp_path):
    outcome = _vision_intent_routes(
        _case(
            "vision.intent_routes",
            samples=[
                {
                    "input": "O que você está vendo na tela?",
                    "route": "read_only",
                },
                {
                    "input": "clique no botão enviar",
                    "route": "click",
                    "value": "botão enviar",
                },
                {
                    "input": "onde está o botão enviar",
                    "route": "grounding",
                    "value": "botao enviar",
                },
                {
                    "input": "clique duas vezes no botão",
                    "route": "none",
                },
            ],
        ),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["routing_accuracy_pct"] == 100.0


def test_structured_intents_validate_safe_and_blocked_sequences(tmp_path):
    outcome = _structured_intents(
        _case("vision.structured_intents"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["destructive_sequence_blocked"] is True
    assert outcome.metrics["safe_sequence"] is True


def test_synthetic_grounding_selects_expected_button(tmp_path):
    outcome = _synthetic_grounding(
        _case("vision.synthetic_grounding"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["target_found"] is True
    assert outcome.metrics["center_x_px"] == 1680
    assert outcome.metrics["center_y_px"] == 929


def test_post_action_verification_requires_observable_evidence(tmp_path):
    outcome = _post_action_verification(
        _case("vision.post_action"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["navigation_verified"] is True
    assert outcome.metrics["focus_verified"] is True
    assert outcome.metrics["inconclusive_rejected"] is True


def test_synthetic_capture_creates_valid_capture(tmp_path):
    outcome = _synthetic_capture(
        _case("vision.synthetic_capture"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["width_px"] == 1366
    assert outcome.metrics["height_px"] == 768
    assert outcome.metrics["capture_bytes"] > 0


def test_live_vision_endpoint_guard_accepts_only_loopback():
    assert _is_loopback_http_endpoint("http://localhost:11434/api/chat") is True
    assert _is_loopback_http_endpoint("http://127.0.0.1:11434/api/chat") is True
    assert _is_loopback_http_endpoint("https://example.com/api/chat") is False


def test_live_capture_skips_when_live_is_disabled(tmp_path):
    outcome = _live_capture(
        _case("vision.live_capture"),
        _context(tmp_path),
        live=False,
    )

    assert outcome.status is BenchmarkStatus.SKIP


def test_live_analysis_skips_when_live_is_disabled(tmp_path):
    outcome = _live_analysis(
        _case("vision.live_analysis"),
        _context(tmp_path),
        live=False,
        timeout_s=1.0,
    )

    assert outcome.status is BenchmarkStatus.SKIP
