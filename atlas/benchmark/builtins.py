"""Safe built-in executors used to validate the benchmark engine itself."""

from __future__ import annotations

from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner


def register_builtin_executors(runner: BenchmarkRunner) -> None:
    """Register deterministic, side-effect-free foundation executors."""

    runner.register_executor("benchmark.noop", _noop)
    runner.register_executor("benchmark.determinism", _determinism)
    runner.register_executor("benchmark.scratch", _scratch)


def _noop(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del case, context
    return CaseOutcome(
        status=BenchmarkStatus.PASS,
        score=100.0,
        metrics={"engine_ready": True},
        details=("Benchmark executor registry is operational.",),
    )


def _determinism(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    del case
    first = context.random().random()
    second = context.random().random()
    passed = first == second
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={"deterministic_seed": passed},
        details=("Per-case seeded simulation is reproducible.",),
    )


def _scratch(case: BenchmarkCase, context: BenchmarkContext) -> CaseOutcome:
    payload = str(case.parameters.get("payload", "atlas-benchmark"))
    path = context.scratch_dir / "probe.txt"
    path.write_text(payload, encoding="utf-8")
    passed = path.read_text(encoding="utf-8") == payload
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics={"scratch_io": passed},
        details=("Isolated scratch workspace is writable.",),
    )
