"""Command-line interface for Atlas Validation Lab."""

from __future__ import annotations

import argparse
from pathlib import Path

from .registry import ScenarioRegistry
from .report import render_console, write_json, write_markdown
from .runner import ScenarioRunner
from .models import BenchmarkPolicy


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atlas_validation")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List registered scenarios")
    list_parser.add_argument("--domain")
    list_parser.add_argument("--execution", choices=["automated", "manual", "planned"])

    run_parser = subparsers.add_parser("run", help="Run Atlas validation scenarios")
    run_parser.add_argument("--domain")
    run_parser.add_argument("--execution", choices=["automated", "manual", "planned"])
    run_parser.add_argument("--json", dest="json_path")
    run_parser.add_argument("--markdown", dest="markdown_path")
    run_parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Repeat safe automated checks and collect p50/p95, CPU and RAM",
    )
    run_parser.add_argument("--iterations", type=int, default=10)
    run_parser.add_argument("--warmup", type=int, default=1)
    run_parser.add_argument("--p50-ms-max", type=float)
    run_parser.add_argument("--p95-ms-max", type=float)
    run_parser.add_argument("--cpu-percent-max", type=float)
    run_parser.add_argument("--memory-delta-mb-max", type=float)

    return parser


def _load(root: Path):
    registry = ScenarioRegistry(root / "validation" / "scenarios")
    return registry.load()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _project_root()
    scenarios = _load(root)

    if args.command in {None, "list"}:
        selected = scenarios
        domain = getattr(args, "domain", None)
        execution = getattr(args, "execution", None)
        if domain:
            selected = [item for item in selected if item.domain == domain.lower()]
        if execution:
            selected = [item for item in selected if item.execution == execution]
        for scenario in selected:
            print(
                f"{scenario.scenario_id:16} {scenario.domain:12} "
                f"{scenario.execution:9} {scenario.title}"
            )
        print(f"\nTotal: {len(selected)} scenario(s)")
        return 0

    runner = ScenarioRunner(root)
    benchmark = None
    if args.benchmark:
        benchmark = BenchmarkPolicy(
            iterations=args.iterations,
            warmup_iterations=args.warmup,
            p50_ms_max=args.p50_ms_max,
            p95_ms_max=args.p95_ms_max,
            cpu_percent_max=args.cpu_percent_max,
            memory_delta_mb_max=args.memory_delta_mb_max,
        )

    results = runner.run_many(
        scenarios,
        domain=args.domain,
        execution=args.execution,
        benchmark=benchmark,
    )
    print(render_console(results))

    if args.json_path:
        write_json(results, root / args.json_path)
    if args.markdown_path:
        write_markdown(results, root / args.markdown_path)

    failures = sum(result.status.value == "FAIL" for result in results)
    return 1 if failures else 0
