from __future__ import annotations

from pathlib import Path

from atlas.benchmark.business_executors import register_business_executors
from atlas.benchmark.catalog import BenchmarkCatalog
from atlas.benchmark.models import BenchmarkKind, BenchmarkStatus
from atlas.benchmark.runner import BenchmarkRunner


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_business_foundation_suite_is_business_simulation():
    project_root = _project_root()
    catalog = BenchmarkCatalog(project_root / "benchmarks" / "suites")
    suite = catalog.get("business_foundation")

    assert suite.kind is BenchmarkKind.BUSINESS_SIMULATION
    assert len(suite.cases) == 6


def test_business_foundation_runs_without_failures():
    project_root = _project_root()
    catalog = BenchmarkCatalog(project_root / "benchmarks" / "suites")
    suite = catalog.get("business_foundation")
    runner = BenchmarkRunner(project_root)
    register_business_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)

    assert run.summary.passed == 6
    assert run.summary.failed == 0
    assert run.summary.errors == 0
    assert all(result.status is BenchmarkStatus.PASS for result in run.results)


def test_frontend_contract_marks_payload_ready():
    project_root = _project_root()
    catalog = BenchmarkCatalog(project_root / "benchmarks" / "suites")
    suite = catalog.get("business_foundation")
    frontend_case = next(
        case for case in suite.cases if case.case_id == "business.frontend_contract"
    )
    runner = BenchmarkRunner(project_root)
    register_business_executors(runner)

    mini_suite = type(suite)(
        suite_id="frontend-only",
        title="Frontend only",
        kind=suite.kind,
        cases=(frontend_case,),
    )
    run = runner.run_suite(mini_suite, atlas_version="test", seed=27)

    assert run.results[0].metrics["frontend_ready"] is True
    assert run.results[0].metrics["dashboard_schema_version"] == "1.0"
