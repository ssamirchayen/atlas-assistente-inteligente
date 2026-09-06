"""CLI for Atlas Benchmark & Validation Lab - Sprint 27."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _atlas_version() -> str:
    override = os.getenv("ATLAS_BENCHMARK_VERSION", "").strip()
    if override:
        return override
    try:
        from atlas.version import ATLAS_VERSION
    except Exception:
        return "unknown"
    return str(ATLAS_VERSION)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_atlas_benchmark")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List benchmark suites")
    list_parser.add_argument("--kind")

    run_parser = subparsers.add_parser("run", help="Run one benchmark suite")
    run_parser.add_argument("suite_id", nargs="?", default="foundation")
    run_parser.add_argument("--seed", type=int, default=27)
    run_parser.add_argument("--version")
    run_parser.add_argument("--no-save", action="store_true")
    run_parser.add_argument(
        "--no-resources",
        action="store_true",
        help="Disable CPU/RAM/GPU telemetry for this benchmark run",
    )
    run_parser.add_argument(
        "--resource-interval-ms",
        type=int,
        default=_env_int("ATLAS_BENCHMARK_RESOURCE_INTERVAL_MS", 100),
    )
    run_parser.add_argument(
        "--gpu-interval-ms",
        type=int,
        default=_env_int("ATLAS_BENCHMARK_GPU_INTERVAL_MS", 1000),
    )
    run_parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live probes such as Ollama readiness and chat",
    )
    run_parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=120.0,
        help="Timeout in seconds for the live Ollama chat probe",
    )
    run_parser.add_argument(
        "--tts-timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds for the live Edge neural TTS probe",
    )
    run_parser.add_argument(
        "--vision-timeout",
        type=float,
        default=_env_float("ATLAS_VISION_TIMEOUT", 120.0),
        help="Timeout in seconds for the live local Vision probe",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    # Local imports keep direct-script bootstrap compatible with Ruff E402.
    from atlas.benchmark.catalog import BenchmarkCatalog
    from atlas.benchmark.report import render_console
    from atlas.benchmark.runtime import BenchmarkRuntimeOptions, execute_suite

    parser = build_parser()
    args = parser.parse_args(argv)

    catalog = BenchmarkCatalog(ROOT / "benchmarks" / "suites")

    if args.command in {None, "list"}:
        suites = catalog.load()
        kind_filter = getattr(args, "kind", None)
        for suite in suites:
            if kind_filter and suite.kind.value != kind_filter:
                continue
            print(f"{suite.suite_id:20} {suite.kind.value:20} {suite.title}")
        return 0

    options = BenchmarkRuntimeOptions(
        live=args.live,
        resource_monitoring=not args.no_resources,
        resource_interval_ms=args.resource_interval_ms,
        gpu_interval_ms=args.gpu_interval_ms,
        ollama_timeout_s=args.ollama_timeout,
        tts_timeout_s=args.tts_timeout,
        vision_timeout_s=args.vision_timeout,
        save_run=not args.no_save,
    )
    run, saved_path = execute_suite(
        ROOT,
        args.suite_id,
        version=args.version or _atlas_version(),
        seed=args.seed,
        options=options,
    )
    print(render_console(run))
    if saved_path is not None:
        print(f"Saved: {saved_path}")

    return 0 if run.summary.failed == 0 and run.summary.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
