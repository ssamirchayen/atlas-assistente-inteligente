from __future__ import annotations

from pathlib import Path

from atlas.benchmark.catalog import BenchmarkCatalog
from atlas.benchmark.models import BenchmarkKind, BenchmarkStatus
from atlas.benchmark.roi_executors import register_roi_productivity_executors
from atlas.benchmark.runner import BenchmarkRunner


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_roi_suite_is_business_simulation_with_seven_cases():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "roi_productivity"
    )

    assert suite.kind is BenchmarkKind.BUSINESS_SIMULATION
    assert len(suite.cases) == 7
    assert suite.metadata["stage"] == 11


def test_roi_suite_runs_without_failures():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "roi_productivity"
    )
    runner = BenchmarkRunner(project_root)
    register_roi_productivity_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)

    assert run.summary.passed == 7
    assert run.summary.failed == 0
    assert run.summary.errors == 0
    assert all(result.status is BenchmarkStatus.PASS for result in run.results)


def test_frontend_contract_is_ready():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "roi_productivity"
    )
    frontend_case = next(
        case for case in suite.cases if case.case_id == "roi.frontend_contract"
    )
    runner = BenchmarkRunner(project_root)
    register_roi_productivity_executors(runner)
    mini_suite = type(suite)(
        suite_id="roi-frontend-only",
        title="ROI frontend only",
        kind=suite.kind,
        cases=(frontend_case,),
    )

    run = runner.run_suite(mini_suite, atlas_version="test", seed=27)

    assert run.results[0].metrics["frontend_ready"] is True
    assert run.results[0].metrics["four_labs"] is True
    assert run.results[0].metrics["dashboard_schema_version"] == "1.0"
