"""Shared runtime for Atlas benchmark CLI and dashboard."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .automation_vision_executors import register_automation_vision_executors
from .builtins import register_builtin_executors
from .business_executors import register_business_executors
from .catalog import BenchmarkCatalog
from .core_executors import register_core_executors
from .helpdesk_executors import register_helpdesk_executors
from .memory_stress_executors import register_memory_stress_executors
from .models import BenchmarkRun
from .resource_monitor import SystemResourceMonitor
from .retail_office_executors import register_retail_office_executors
from .roi_executors import register_roi_productivity_executors
from .runner import BenchmarkRunner
from .school_executors import register_school_executors
from .storage import BenchmarkRunStore
from .voice_executors import register_voice_executors


@dataclass(frozen=True, slots=True)
class BenchmarkRuntimeOptions:
    """Execution options shared by command line and mini frontend."""

    live: bool = False
    resource_monitoring: bool = True
    resource_interval_ms: int = 100
    gpu_interval_ms: int = 1000
    ollama_timeout_s: float = 120.0
    tts_timeout_s: float = 30.0
    vision_timeout_s: float = 120.0
    save_run: bool = True

    def __post_init__(self) -> None:
        if self.resource_interval_ms <= 0:
            raise ValueError("resource_interval_ms must be positive")
        if self.gpu_interval_ms <= 0:
            raise ValueError("gpu_interval_ms must be positive")
        for name in ("ollama_timeout_s", "tts_timeout_s", "vision_timeout_s"):
            if float(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")


def atlas_version() -> str:
    """Return the running Atlas version with an optional benchmark override."""

    override = os.getenv("ATLAS_BENCHMARK_VERSION", "").strip()
    if override:
        return override
    try:
        from atlas.version import ATLAS_VERSION
    except Exception:
        return "unknown"
    return str(ATLAS_VERSION)


def build_registered_runner(
    project_root: Path,
    *,
    options: BenchmarkRuntimeOptions,
) -> BenchmarkRunner:
    """Build one runner with every Sprint 27 executor registered."""

    monitor_factory = None
    if options.resource_monitoring:

        def monitor_factory():
            return SystemResourceMonitor(
                sample_interval_ms=options.resource_interval_ms,
                gpu_interval_ms=options.gpu_interval_ms,
            )

    runner = BenchmarkRunner(
        project_root,
        resource_monitor_factory=monitor_factory,
    )
    register_builtin_executors(runner)
    register_core_executors(
        runner,
        live=options.live,
        ollama_timeout_s=options.ollama_timeout_s,
    )
    register_voice_executors(
        runner,
        live=options.live,
        tts_timeout_s=options.tts_timeout_s,
    )
    register_automation_vision_executors(
        runner,
        live=options.live,
        vision_timeout_s=options.vision_timeout_s,
    )
    register_memory_stress_executors(runner)
    register_business_executors(runner)
    register_school_executors(runner)
    register_helpdesk_executors(runner)
    register_retail_office_executors(runner)
    register_roi_productivity_executors(runner)
    return runner


def execute_suite(
    project_root: Path,
    suite_id: str,
    *,
    version: str | None = None,
    seed: int = 27,
    options: BenchmarkRuntimeOptions | None = None,
) -> tuple[BenchmarkRun, Path | None]:
    """Execute and optionally persist one benchmark suite."""

    root = Path(project_root).resolve()
    runtime_options = options or BenchmarkRuntimeOptions()
    catalog = BenchmarkCatalog(root / "benchmarks" / "suites")
    suite = catalog.get(suite_id)
    runner = build_registered_runner(root, options=runtime_options)
    run = runner.run_suite(
        suite,
        atlas_version=version or atlas_version(),
        seed=seed,
        metadata={
            "sprint": 27,
            "stage": int(suite.metadata.get("stage", 12)),
            "resource_monitoring": runtime_options.resource_monitoring,
            "resource_interval_ms": runtime_options.resource_interval_ms,
            "gpu_interval_ms": runtime_options.gpu_interval_ms,
            "live": runtime_options.live,
            "ollama_timeout_s": runtime_options.ollama_timeout_s,
            "tts_timeout_s": runtime_options.tts_timeout_s,
            "vision_timeout_s": runtime_options.vision_timeout_s,
            "source": "benchmark_runtime",
        },
    )

    saved_path = None
    if runtime_options.save_run:
        store = BenchmarkRunStore(root / "data" / "benchmark_runs")
        saved_path = store.save(run)
    return run, saved_path
