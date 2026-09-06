"""Deterministic orchestration engine for Atlas Benchmark."""

from __future__ import annotations

import hashlib
import random
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

from .models import (
    BenchmarkCase,
    BenchmarkRun,
    BenchmarkStatus,
    BenchmarkSuite,
    BenchmarkSummary,
    CaseOutcome,
    CaseResult,
)
from .resource_monitor import ResourceSummary

Executor = Callable[[BenchmarkCase, "BenchmarkContext"], CaseOutcome | bool]


class CaseResourceMonitor(Protocol):
    """Minimal monitor contract accepted by the runner."""

    def start(self) -> None: ...

    def stop(self) -> ResourceSummary: ...


ResourceMonitorFactory = Callable[[], CaseResourceMonitor]


@dataclass(slots=True)
class BenchmarkContext:
    """Isolated context passed to a benchmark executor."""

    project_root: Path
    scratch_dir: Path
    run_id: str
    seed: int
    case_seed: int
    shared: dict[str, object] = field(default_factory=dict)

    def random(self) -> random.Random:
        """Return a deterministic RNG unique to this case."""

        return random.Random(self.case_seed)


class BenchmarkRunner:
    """Execute benchmark suites without coupling them to Atlas operational state."""

    def __init__(
        self,
        project_root: Path,
        *,
        clock: Callable[[], float] | None = None,
        resource_monitor_factory: ResourceMonitorFactory | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self._clock = clock or time.perf_counter
        self._resource_monitor_factory = resource_monitor_factory
        self._executors: dict[str, Executor] = {}

    def register_executor(self, name: str, executor: Executor) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("executor name cannot be empty")
        if normalized in self._executors:
            raise ValueError(f"executor already registered: {normalized}")
        self._executors[normalized] = executor

    def run_suite(
        self,
        suite: BenchmarkSuite,
        *,
        atlas_version: str = "unknown",
        seed: int = 27,
        metadata: dict[str, object] | None = None,
    ) -> BenchmarkRun:
        run_id = self._new_run_id()
        started = self._now_iso()
        shared: dict[str, object] = {}

        with tempfile.TemporaryDirectory(prefix="atlas-benchmark-") as temp_dir:
            scratch_root = Path(temp_dir)
            results = tuple(
                self._run_case(
                    case,
                    run_id=run_id,
                    seed=seed,
                    scratch_root=scratch_root,
                    shared=shared,
                )
                for case in suite.cases
            )

        finished = self._now_iso()
        summary = BenchmarkSummary.from_results(results)
        return BenchmarkRun(
            run_id=run_id,
            suite_id=suite.suite_id,
            suite_title=suite.title,
            kind=suite.kind,
            atlas_version=str(atlas_version),
            started_at_utc=started,
            finished_at_utc=finished,
            seed=int(seed),
            results=results,
            summary=summary,
            metadata=dict(metadata or {}),
        )

    def _run_case(
        self,
        case: BenchmarkCase,
        *,
        run_id: str,
        seed: int,
        scratch_root: Path,
        shared: dict[str, object],
    ) -> CaseResult:
        if not case.enabled:
            return CaseResult(
                case_id=case.case_id,
                title=case.title,
                domain=case.domain,
                kind=case.kind,
                status=BenchmarkStatus.SKIP,
                score=0.0,
                weight=case.weight,
                duration_ms=0.0,
                details=("Case disabled by suite configuration.",),
            )

        executor = self._executors.get(case.executor)
        if executor is None:
            return CaseResult(
                case_id=case.case_id,
                title=case.title,
                domain=case.domain,
                kind=case.kind,
                status=BenchmarkStatus.ERROR,
                score=0.0,
                weight=case.weight,
                duration_ms=0.0,
                error=f"Executor not registered: {case.executor}",
            )

        case_scratch = scratch_root / self._safe_segment(case.case_id)
        case_scratch.mkdir(parents=True, exist_ok=True)
        case_seed = self._derive_seed(seed, case.case_id)
        context = BenchmarkContext(
            project_root=self.project_root,
            scratch_dir=case_scratch,
            run_id=run_id,
            seed=seed,
            case_seed=case_seed,
            shared=shared,
        )

        monitor = None
        monitor_error: str | None = None
        if self._resource_monitor_factory is not None:
            try:
                monitor = self._resource_monitor_factory()
                monitor.start()
            except Exception as exc:
                monitor = None
                monitor_error = f"{type(exc).__name__}: {exc}"

        started = self._clock()
        try:
            raw_outcome = executor(case, context)
            outcome = self._normalize_outcome(raw_outcome)
            error = None
        except Exception as exc:  # benchmark failures must not stop the suite
            outcome = CaseOutcome(
                status=BenchmarkStatus.ERROR,
                score=0.0,
                details=("Executor raised an exception.",),
            )
            error = f"{type(exc).__name__}: {exc}"
        duration_ms = max(0.0, (self._clock() - started) * 1000.0)

        metrics = dict(outcome.metrics)
        if monitor is not None:
            try:
                metrics.update(monitor.stop().to_metrics())
            except Exception as exc:
                monitor_error = f"{type(exc).__name__}: {exc}"
        if monitor_error:
            metrics["resource.monitor_error"] = monitor_error

        return CaseResult(
            case_id=case.case_id,
            title=case.title,
            domain=case.domain,
            kind=case.kind,
            status=outcome.status,
            score=float(outcome.score),
            weight=case.weight,
            duration_ms=round(duration_ms, 3),
            metrics=metrics,
            details=tuple(outcome.details),
            error=error,
        )

    @staticmethod
    def _normalize_outcome(raw: CaseOutcome | bool) -> CaseOutcome:
        if isinstance(raw, CaseOutcome):
            return raw
        if isinstance(raw, bool):
            return CaseOutcome(
                status=BenchmarkStatus.PASS if raw else BenchmarkStatus.FAIL,
                score=100.0 if raw else 0.0,
            )
        raise TypeError(
            "Benchmark executor must return CaseOutcome or bool, "
            f"got {type(raw).__name__}"
        )

    @staticmethod
    def _derive_seed(seed: int, case_id: str) -> int:
        payload = f"{int(seed)}:{case_id}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        return int.from_bytes(digest[:8], "big", signed=False)

    @staticmethod
    def _safe_segment(value: str) -> str:
        return "".join(
            char if char.isalnum() or char in "._-" else "_" for char in value
        )[:96]

    @staticmethod
    def _new_run_id() -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
