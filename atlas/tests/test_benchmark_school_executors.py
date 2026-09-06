from __future__ import annotations

from pathlib import Path

from atlas.benchmark.catalog import BenchmarkCatalog
from atlas.benchmark.models import BenchmarkKind, BenchmarkStatus
from atlas.benchmark.runner import BenchmarkRunner
from atlas.benchmark.school_executors import register_school_executors


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_school_suite_is_business_simulation():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "school_leads"
    )

    assert suite.kind is BenchmarkKind.BUSINESS_SIMULATION
    assert len(suite.cases) == 7


def test_school_suite_runs_without_failures():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "school_leads"
    )
    runner = BenchmarkRunner(project_root)
    register_school_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)

    assert run.summary.total == 7
    assert run.summary.passed == 7
    assert run.summary.failed == 0
    assert run.summary.errors == 0
    assert all(result.status is BenchmarkStatus.PASS for result in run.results)


def test_school_frontend_contract_is_marked_ready():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "school_leads"
    )
    runner = BenchmarkRunner(project_root)
    register_school_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)
    frontend = next(
        result for result in run.results if result.case_id == "school.frontend_contract"
    )

    assert frontend.metrics["frontend_ready"] is True
    assert frontend.metrics["dashboard_schema_version"] == "1.0"
