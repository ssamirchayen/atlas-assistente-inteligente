from __future__ import annotations

from pathlib import Path

from atlas.benchmark.catalog import BenchmarkCatalog
from atlas.benchmark.helpdesk_executors import register_helpdesk_executors
from atlas.benchmark.models import BenchmarkKind, BenchmarkStatus
from atlas.benchmark.runner import BenchmarkRunner


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_helpdesk_suite_is_business_simulation():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "helpdesk_provisioning"
    )

    assert suite.kind is BenchmarkKind.BUSINESS_SIMULATION
    assert len(suite.cases) == 8


def test_helpdesk_suite_runs_without_failures():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "helpdesk_provisioning"
    )
    runner = BenchmarkRunner(project_root)
    register_helpdesk_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)

    assert run.summary.total == 8
    assert run.summary.passed == 8
    assert run.summary.failed == 0
    assert run.summary.errors == 0
    assert all(result.status is BenchmarkStatus.PASS for result in run.results)


def test_helpdesk_frontend_contract_is_marked_ready():
    project_root = _project_root()
    suite = BenchmarkCatalog(project_root / "benchmarks" / "suites").get(
        "helpdesk_provisioning"
    )
    runner = BenchmarkRunner(project_root)
    register_helpdesk_executors(runner)

    run = runner.run_suite(suite, atlas_version="test", seed=27)
    frontend = next(
        result
        for result in run.results
        if result.case_id == "helpdesk.frontend_contract"
    )

    assert frontend.metrics["frontend_ready"] is True
    assert frontend.metrics["dashboard_schema_version"] == "1.0"
