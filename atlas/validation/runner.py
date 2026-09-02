"""Safe, deterministic runner for Atlas validation scenarios."""

from __future__ import annotations

import time
from math import ceil
from pathlib import Path
from typing import Any, Callable

import psutil

from .models import (
    BenchmarkPolicy,
    ScenarioDefinition,
    ScenarioResult,
    ScenarioStatus,
)


class ScenarioRunner:
    """Evaluate automated checks while keeping manual/critical flows non-invasive."""

    def __init__(
        self,
        project_root: Path,
        *,
        clock: Callable[[], float] | None = None,
        process: Any | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self._clock = clock or time.perf_counter
        self._process = process
        self._process_unavailable = False

    def run(
        self,
        scenario: ScenarioDefinition,
        *,
        benchmark: BenchmarkPolicy | None = None,
    ) -> ScenarioResult:
        if scenario.execution == "manual":
            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                title=scenario.title,
                domain=scenario.domain,
                status=ScenarioStatus.MANUAL,
                details=["Requires controlled manual/E2E execution."],
            )
        if scenario.execution == "planned":
            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                title=scenario.title,
                domain=scenario.domain,
                status=ScenarioStatus.PLANNED,
                details=["Scenario reserved for a future Atlas capability."],
            )

        policy = benchmark or scenario.benchmark
        if policy is not None:
            return self._run_benchmark(scenario, policy)

        started = self._clock()
        details: list[str] = []
        status = ScenarioStatus.PASS
        for check in scenario.checks:
            ok, message = self._evaluate_check(check)
            details.append(message)
            if not ok:
                status = ScenarioStatus.FAIL

        duration_ms = (self._clock() - started) * 1000
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            title=scenario.title,
            domain=scenario.domain,
            status=status,
            duration_ms=duration_ms,
            details=details,
        )

    def run_many(
        self,
        scenarios: list[ScenarioDefinition],
        *,
        domain: str | None = None,
        execution: str | None = None,
        benchmark: BenchmarkPolicy | None = None,
    ) -> list[ScenarioResult]:
        selected = scenarios
        if domain:
            selected = [item for item in selected if item.domain == domain.lower()]
        if execution:
            selected = [
                item for item in selected if item.execution == execution.lower()
            ]
        return [self.run(item, benchmark=benchmark) for item in selected]

    def _run_benchmark(
        self,
        scenario: ScenarioDefinition,
        policy: BenchmarkPolicy,
    ) -> ScenarioResult:
        """Repeat only declarative checks and collect local process metrics."""

        status = ScenarioStatus.PASS
        details: list[str] = []

        for _ in range(policy.warmup_iterations):
            for check in scenario.checks:
                ok, _ = self._evaluate_check(check)
                if not ok:
                    status = ScenarioStatus.FAIL

        cpu_before = self._cpu_seconds()
        memory_start = self._memory_rss_mb()
        memory_peak = memory_start
        latencies_ms: list[float] = []
        overall_started = self._clock()

        for iteration in range(1, policy.iterations + 1):
            iteration_started = self._clock()
            iteration_failed = False
            iteration_details: list[str] = []

            for check in scenario.checks:
                ok, message = self._evaluate_check(check)
                iteration_details.append(message)
                if not ok:
                    iteration_failed = True

            latencies_ms.append(
                max(0.0, (self._clock() - iteration_started) * 1000)
            )
            memory_peak = max(memory_peak, self._memory_rss_mb())

            if iteration_failed:
                status = ScenarioStatus.FAIL
                details.append(f"iteration {iteration}: check failed")
                details.extend(iteration_details)

        overall_seconds = max(0.0, self._clock() - overall_started)
        cpu_seconds = max(0.0, self._cpu_seconds() - cpu_before)
        memory_end = self._memory_rss_mb()
        memory_peak = max(memory_peak, memory_end)
        memory_delta = max(0.0, memory_peak - memory_start)
        cpu_percent = (
            (cpu_seconds / overall_seconds) * 100
            if overall_seconds > 0
            else 0.0
        )

        metrics: dict[str, float | int] = {
            "iterations": policy.iterations,
            "warmup_iterations": policy.warmup_iterations,
            "latency_min_ms": round(min(latencies_ms), 3),
            "latency_p50_ms": round(self._percentile(latencies_ms, 50), 3),
            "latency_p95_ms": round(self._percentile(latencies_ms, 95), 3),
            "latency_max_ms": round(max(latencies_ms), 3),
            "cpu_time_ms": round(cpu_seconds * 1000, 3),
            "cpu_percent": round(cpu_percent, 3),
            "memory_start_mb": round(memory_start, 3),
            "memory_end_mb": round(memory_end, 3),
            "memory_peak_mb": round(memory_peak, 3),
            "memory_delta_mb": round(memory_delta, 3),
        }

        budget_failures = self._budget_failures(policy, metrics)
        if budget_failures:
            status = ScenarioStatus.FAIL
            details.extend(budget_failures)
        elif status is ScenarioStatus.PASS:
            details.append(
                f"benchmark completed: {policy.iterations} measured iteration(s)"
            )

        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            title=scenario.title,
            domain=scenario.domain,
            status=status,
            duration_ms=overall_seconds * 1000,
            details=details,
            metrics=metrics,
        )

    def _cpu_seconds(self) -> float:
        process = self._metrics_process()
        if process is None:
            return time.process_time()
        value = process.cpu_times()
        return float(value.user) + float(value.system)

    def _memory_rss_mb(self) -> float:
        process = self._metrics_process()
        if process is not None:
            return float(process.memory_info().rss) / (1024 * 1024)

        try:
            import resource

            rss = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # Linux/BSD report KiB; macOS reports bytes.
            if rss > 1024 * 1024 * 16:
                return rss / (1024 * 1024)
            return rss / 1024
        except (ImportError, OSError, ValueError):
            return 0.0

    def _metrics_process(self) -> Any | None:
        if self._process is not None:
            return self._process
        if self._process_unavailable:
            return None
        try:
            self._process = psutil.Process()
        except psutil.Error:
            self._process_unavailable = True
            return None
        return self._process

    @staticmethod
    def _percentile(values: list[float], percentile: int) -> float:
        ordered = sorted(values)
        index = max(0, ceil((percentile / 100) * len(ordered)) - 1)
        return ordered[index]

    @staticmethod
    def _budget_failures(
        policy: BenchmarkPolicy,
        metrics: dict[str, float | int],
    ) -> list[str]:
        budgets = (
            ("latency_p50_ms", policy.p50_ms_max),
            ("latency_p95_ms", policy.p95_ms_max),
            ("cpu_percent", policy.cpu_percent_max),
            ("memory_delta_mb", policy.memory_delta_mb_max),
        )
        failures: list[str] = []
        for metric, limit in budgets:
            measured = float(metrics[metric])
            if limit is not None and measured > limit:
                failures.append(
                    f"budget exceeded: {metric}={measured:.3f} > {limit:.3f}"
                )
        return failures

    def _evaluate_check(self, check: dict[str, Any]) -> tuple[bool, str]:
        check_type = str(check.get("type", "")).lower()
        if check_type == "path_exists":
            return self._path_exists(check)
        if check_type == "path_not_exists":
            return self._path_not_exists(check)
        if check_type == "text_contains":
            return self._text_contains(check, expected=True)
        if check_type == "text_not_contains":
            return self._text_contains(check, expected=False)
        return False, f"Unknown check type: {check_type or '<empty>'}"

    def _resolve(self, value: str) -> Path:
        candidate = (self.project_root / value).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"Check path escapes project root: {value}") from exc
        return candidate

    def _path_exists(self, check: dict[str, Any]) -> tuple[bool, str]:
        value = str(check.get("path", ""))
        path = self._resolve(value)
        ok = path.exists()
        return ok, f"path_exists {value}: {'OK' if ok else 'MISSING'}"

    def _path_not_exists(self, check: dict[str, Any]) -> tuple[bool, str]:
        value = str(check.get("path", ""))
        path = self._resolve(value)
        ok = not path.exists()
        return ok, f"path_not_exists {value}: {'OK' if ok else 'PRESENT'}"

    def _text_contains(
        self, check: dict[str, Any], *, expected: bool
    ) -> tuple[bool, str]:
        value = str(check.get("path", ""))
        needle = str(check.get("text", ""))
        path = self._resolve(value)
        if not path.is_file():
            return False, f"text check {value}: FILE MISSING"
        content = path.read_text(encoding="utf-8", errors="replace")
        found = needle in content
        ok = found if expected else not found
        verb = "contains" if expected else "not_contains"
        return ok, f"{verb} {value} -> {needle!r}: {'OK' if ok else 'FAIL'}"
