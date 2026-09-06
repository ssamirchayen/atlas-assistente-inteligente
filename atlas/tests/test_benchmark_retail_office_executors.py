from __future__ import annotations

from pathlib import Path

from atlas.benchmark.catalog import BenchmarkCatalog
from atlas.benchmark.models import BenchmarkKind, BenchmarkStatus
from atlas.benchmark.retail_office_executors import register_retail_office_executors
from atlas.benchmark.runner import BenchmarkRunner


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_retail_office_suite_is_business_simulation():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "retail_office"
    )

    assert suite.kind is BenchmarkKind.BUSINESS_SIMULATION
    assert len(suite.cases) == 10


def test_retail_office_suite_runs_without_failures():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "retail_office"
    )
    runner = BenchmarkRunner(project_root)
    register_retail_office_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)

    assert run.summary.total == 10
    assert run.summary.passed == 10
    assert run.summary.failed == 0
    assert run.summary.errors == 0
    assert all(result.status is BenchmarkStatus.PASS for result in run.results)


def test_retail_office_frontend_contracts_are_marked_ready():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "retail_office"
    )
    runner = BenchmarkRunner(project_root)
    register_retail_office_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)
    frontend_results = {
        result.case_id: result
        for result in run.results
        if result.case_id in {
            "retail.frontend_contract",
            "office.frontend_contract",
        }
    }

    assert frontend_results["retail.frontend_contract"].metrics["frontend_ready"] is True
    assert frontend_results["office.frontend_contract"].metrics["frontend_ready"] is True
    assert (
        frontend_results["retail.frontend_contract"].metrics[
            "dashboard_schema_version"
        ]
        == "1.0"
    )
    assert (
        frontend_results["office.frontend_contract"].metrics[
            "dashboard_schema_version"
        ]
        == "1.0"
    )
