from __future__ import annotations

from atlas.benchmark.models import (
    BenchmarkCase,
    BenchmarkKind,
    BenchmarkStatus,
    BenchmarkSuite,
    CaseOutcome,
)
from atlas.benchmark.runner import BenchmarkRunner


def _suite(*cases: BenchmarkCase) -> BenchmarkSuite:
    return BenchmarkSuite(
        suite_id="test",
        title="Test suite",
        kind=BenchmarkKind.TECHNICAL,
        cases=tuple(cases),
    )


def test_runner_normalizes_boolean_result(tmp_path):
    case = BenchmarkCase(
        case_id="core.ok",
        title="OK",
        domain="core",
        executor="test.ok",
    )
    runner = BenchmarkRunner(tmp_path)
    runner.register_executor("test.ok", lambda _case, _context: True)

    run = runner.run_suite(_suite(case), atlas_version="1.0.0")

    assert run.results[0].status is BenchmarkStatus.PASS
    assert run.summary.weighted_score == 100.0


def test_runner_captures_executor_exception(tmp_path):
    case = BenchmarkCase(
        case_id="core.error",
        title="Error",
        domain="core",
        executor="test.error",
    )
    runner = BenchmarkRunner(tmp_path)

    def explode(_case, _context):
        raise RuntimeError("boom")

    runner.register_executor("test.error", explode)
    run = runner.run_suite(_suite(case))

    result = run.results[0]
    assert result.status is BenchmarkStatus.ERROR
    assert "RuntimeError: boom" == result.error


def test_runner_seed_is_deterministic_per_case(tmp_path):
    case = BenchmarkCase(
        case_id="simulation.seed",
        title="Seed",
        domain="simulation",
        executor="test.seed",
    )
    seen = []

    def capture(_case, context):
        seen.append(context.random().random())
        return CaseOutcome(metrics={"seed": context.case_seed})

    runner = BenchmarkRunner(tmp_path)
    runner.register_executor("test.seed", capture)
    runner.run_suite(_suite(case), seed=42)
    runner.run_suite(_suite(case), seed=42)

    assert seen[0] == seen[1]


def test_runner_marks_missing_executor_as_error(tmp_path):
    case = BenchmarkCase(
        case_id="core.missing",
        title="Missing",
        domain="core",
        executor="not.registered",
    )
    run = BenchmarkRunner(tmp_path).run_suite(_suite(case))

    assert run.results[0].status is BenchmarkStatus.ERROR
    assert "not.registered" in (run.results[0].error or "")


def test_runner_merges_resource_metrics(tmp_path):
    from atlas.benchmark.resource_monitor import ResourceSummary

    class FakeMonitor:
        def start(self):
            return None

        def stop(self):
            return ResourceSummary(
                sample_count=2,
                process_cpu_mean_pct=12.5,
                process_rss_peak_mb=222.0,
            )

    case = BenchmarkCase(
        case_id="core.resources",
        title="Resources",
        domain="core",
        executor="test.resources",
    )
    runner = BenchmarkRunner(
        tmp_path,
        resource_monitor_factory=FakeMonitor,
    )
    runner.register_executor(
        "test.resources",
        lambda _case, _context: CaseOutcome(metrics={"custom": 1}),
    )

    run = runner.run_suite(_suite(case))
    metrics = run.results[0].metrics

    assert metrics["custom"] == 1
    assert metrics["resource.sample_count"] == 2
    assert metrics["resource.process_cpu_mean_pct"] == 12.5
    assert metrics["resource.process_rss_peak_mb"] == 222.0
