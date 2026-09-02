from collections import namedtuple

from atlas.validation.models import (
    BenchmarkPolicy,
    ScenarioDefinition,
    ScenarioStatus,
)
from atlas.validation.runner import ScenarioRunner


_CpuTimes = namedtuple("CpuTimes", "user system")
_MemoryInfo = namedtuple("MemoryInfo", "rss")


class _FakeProcess:
    def __init__(self) -> None:
        self._cpu = iter((_CpuTimes(1.0, 0.5), _CpuTimes(1.002, 0.501)))
        self._memory = iter(
            (
                _MemoryInfo(100 * 1024 * 1024),
                _MemoryInfo(101 * 1024 * 1024),
                _MemoryInfo(103 * 1024 * 1024),
                _MemoryInfo(102 * 1024 * 1024),
                _MemoryInfo(102 * 1024 * 1024),
            )
        )

    def cpu_times(self):
        return next(self._cpu)

    def memory_info(self):
        return next(self._memory)


def _clock():
    values = iter((0.0, 0.0, 0.001, 0.001, 0.003, 0.003, 0.006, 0.006))
    return lambda: next(values)


def _scenario(tmp_path) -> ScenarioDefinition:
    (tmp_path / "atlas.txt").write_text("ok", encoding="utf-8")
    return ScenarioDefinition.from_dict(
        {
            "id": "PERF-001",
            "title": "Runner benchmark",
            "domain": "performance",
            "execution": "automated",
            "checks": [{"type": "path_exists", "path": "atlas.txt"}],
        }
    )


def test_benchmark_calculates_p50_p95_cpu_and_memory(tmp_path) -> None:
    result = ScenarioRunner(
        tmp_path,
        clock=_clock(),
        process=_FakeProcess(),
    ).run(
        _scenario(tmp_path),
        benchmark=BenchmarkPolicy(iterations=3, warmup_iterations=1),
    )

    assert result.status is ScenarioStatus.PASS
    assert result.metrics["latency_p50_ms"] == 2.0
    assert result.metrics["latency_p95_ms"] == 3.0
    assert result.metrics["memory_delta_mb"] == 3.0
    assert result.metrics["cpu_time_ms"] == 3.0
    assert result.metrics["iterations"] == 3


def test_benchmark_fails_when_p95_budget_is_exceeded(tmp_path) -> None:
    result = ScenarioRunner(
        tmp_path,
        clock=_clock(),
        process=_FakeProcess(),
    ).run(
        _scenario(tmp_path),
        benchmark=BenchmarkPolicy(
            iterations=3,
            warmup_iterations=0,
            p95_ms_max=2.5,
        ),
    )

    assert result.status is ScenarioStatus.FAIL
    assert result.metrics["latency_p95_ms"] == 3.0
    assert any("budget exceeded" in detail for detail in result.details)


def test_manual_scenario_is_never_benchmarked(tmp_path) -> None:
    scenario = ScenarioDefinition.from_dict(
        {
            "id": "MANUAL-001",
            "title": "Manual",
            "domain": "vision",
            "execution": "manual",
        }
    )

    result = ScenarioRunner(tmp_path).run(
        scenario,
        benchmark=BenchmarkPolicy(iterations=3),
    )

    assert result.status is ScenarioStatus.MANUAL
    assert result.metrics == {}
