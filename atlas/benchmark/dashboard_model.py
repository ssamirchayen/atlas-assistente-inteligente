"""Presentation model for the Sprint 27 Atlas Benchmark mini frontend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog import BenchmarkCatalog
from .helpdesk_simulation import HelpDeskScenario, HelpDeskSimulationEngine
from .models import BenchmarkRun
from .retail_office_simulation import (
    OfficeScenario,
    OfficeSimulationEngine,
    RetailScenario,
    RetailSimulationEngine,
)
from .roi_productivity import (
    ProductivityEngine,
    collect_measured_run_evidence,
    helpdesk_snapshot,
    office_snapshot,
    portfolio_dashboard_payload,
    retail_snapshot,
    school_snapshot,
)
from .school_simulation import SchoolLeadScenario, SchoolLeadSimulationEngine
from .storage import BenchmarkRunStore


@dataclass(frozen=True, slots=True)
class SuiteCard:
    suite_id: str
    title: str
    kind: str
    case_count: int
    stage: int
    live_capable: bool


@dataclass(frozen=True, slots=True)
class RunCard:
    run_id: str
    suite_id: str
    title: str
    version: str
    success_rate_pct: float
    weighted_score: float
    passed: int
    failed: int
    errors: int
    skipped: int
    evaluated: int
    finished_at_utc: str
    live: bool


def _case_scenario(
    project_root: Path,
    suite_id: str,
    case_id: str,
) -> dict[str, object]:
    catalog = BenchmarkCatalog(project_root / "benchmarks" / "suites")
    suite = catalog.get(suite_id)
    case = next((item for item in suite.cases if item.case_id == case_id), None)
    if case is None:
        raise ValueError(f"case not found: {suite_id}/{case_id}")
    raw = case.parameters.get("scenario")
    if not isinstance(raw, dict):
        raise ValueError(f"scenario missing: {suite_id}/{case_id}")
    return dict(raw)


def suite_cards(project_root: Path) -> tuple[SuiteCard, ...]:
    """Return compact suite metadata for the dashboard selector."""

    root = Path(project_root).resolve()
    catalog = BenchmarkCatalog(root / "benchmarks" / "suites")
    cards = []
    for suite in catalog.load():
        live_capable = any(
            "live" in case.tags or "ollama" in case.tags or "vision" in case.tags
            for case in suite.cases
        )
        cards.append(
            SuiteCard(
                suite_id=suite.suite_id,
                title=suite.title,
                kind=suite.kind.value,
                case_count=len(suite.cases),
                stage=int(suite.metadata.get("stage", 0)),
                live_capable=live_capable,
            )
        )
    return tuple(cards)


def build_portfolio_payload(
    project_root: Path,
    *,
    max_measured_runs: int = 8,
) -> dict[str, object]:
    """Build the synthetic business portfolio shown by the frontend."""

    root = Path(project_root).resolve()
    school = SchoolLeadSimulationEngine().simulate(
        SchoolLeadScenario.from_dict(
            _case_scenario(root, "school_leads", "school.baseline_vs_atlas")
        )
    )
    helpdesk = HelpDeskSimulationEngine().simulate(
        HelpDeskScenario.from_dict(
            _case_scenario(
                root,
                "helpdesk_provisioning",
                "helpdesk.baseline_vs_atlas",
            )
        )
    )
    retail = RetailSimulationEngine().simulate(
        RetailScenario.from_dict(
            _case_scenario(root, "retail_office", "retail.baseline_vs_atlas")
        )
    )
    office = OfficeSimulationEngine().simulate(
        OfficeScenario.from_dict(
            _case_scenario(root, "retail_office", "office.baseline_vs_atlas")
        )
    )
    snapshots = (
        school_snapshot(school),
        helpdesk_snapshot(helpdesk),
        retail_snapshot(retail),
        office_snapshot(office),
    )
    portfolio = ProductivityEngine().consolidate(snapshots)
    measured = collect_measured_run_evidence(
        root / "data" / "benchmark_runs",
        max_runs=max_measured_runs,
    )
    return portfolio_dashboard_payload(portfolio, measured_runs=measured)


def run_card(run: BenchmarkRun) -> RunCard:
    """Convert a complete benchmark run into a frontend summary card."""

    summary = run.summary
    return RunCard(
        run_id=run.run_id,
        suite_id=run.suite_id,
        title=run.suite_title,
        version=run.atlas_version,
        success_rate_pct=summary.success_rate,
        weighted_score=summary.weighted_score,
        passed=summary.passed,
        failed=summary.failed,
        errors=summary.errors,
        skipped=summary.skipped,
        evaluated=summary.evaluated,
        finished_at_utc=run.finished_at_utc,
        live=bool(run.metadata.get("live", False)),
    )


def recent_run_cards(
    project_root: Path,
    *,
    limit: int = 12,
) -> tuple[RunCard, ...]:
    """Load recent local benchmark runs without failing on one corrupt file."""

    if limit <= 0:
        return ()
    root = Path(project_root).resolve()
    store = BenchmarkRunStore(root / "data" / "benchmark_runs")
    cards: list[RunCard] = []
    for run_id in reversed(store.list_run_ids()):
        try:
            run = store.load(run_id)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        cards.append(run_card(run))
        if len(cards) >= max(0, int(limit)):
            break
    return tuple(cards)
