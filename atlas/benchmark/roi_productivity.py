"""Consolidated ROI and productivity analysis for Sprint 27 stage 11.

This module keeps three evidence classes intentionally separate:

* measured: technical observations collected by the benchmark runner;
* simulated: synthetic operational projections from the business labs;
* economic_projection: monetary interpretation of simulated human capacity.

Economic values describe potential reusable capacity. They are not guaranteed
cash savings, revenue, head-count reduction, or commercial outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .helpdesk_simulation import HelpDeskSimulationResult
from .models import BenchmarkKind
from .retail_office_simulation import OfficeSimulationResult, RetailSimulationResult
from .school_simulation import SchoolLeadSimulationResult
from .storage import BenchmarkRunStore


class EvidenceKind(StrEnum):
    """Provenance labels exposed to reports and the future mini frontend."""

    MEASURED = "measured"
    SIMULATED = "simulated"
    ECONOMIC_PROJECTION = "economic_projection"


@dataclass(frozen=True, slots=True)
class ProductivitySnapshot:
    """Normalized operational inputs from one synthetic business lab."""

    lab_id: str
    title: str
    period_label: str
    volume: float
    automation_rate_pct: float
    hourly_cost_brl: float
    manual_human_hours: float
    atlas_human_hours: float
    manual_throughput_per_human_hour: float
    atlas_throughput_per_human_hour: float
    manual_expected_errors: float
    atlas_expected_errors: float
    manual_response_minutes: float | None = None
    atlas_response_minutes: float | None = None
    source: str = "synthetic_simulation"

    def __post_init__(self) -> None:
        if not self.lab_id.strip() or not self.title.strip():
            raise ValueError("lab_id and title cannot be empty")
        if not self.period_label.strip() or not self.source.strip():
            raise ValueError("period_label and source cannot be empty")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if not 0.0 <= self.automation_rate_pct <= 100.0:
            raise ValueError("automation_rate_pct must be between 0 and 100")
        for name in (
            "hourly_cost_brl",
            "manual_human_hours",
            "atlas_human_hours",
            "manual_throughput_per_human_hour",
            "atlas_throughput_per_human_hour",
            "manual_expected_errors",
            "atlas_expected_errors",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        for name in ("manual_response_minutes", "atlas_response_minutes"):
            value = getattr(self, name)
            if value is not None and float(value) < 0:
                raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True, slots=True)
class ProductivityAnalysis:
    """Calculated productivity metrics for one normalized lab."""

    snapshot: ProductivitySnapshot
    human_hours_liberated: float
    human_time_reduction_pct: float
    throughput_gain_pct: float
    response_reduction_pct: float | None
    expected_error_reduction_pct: float | None
    human_intervention_rate_pct: float
    potential_capacity_value_brl: float
    annual_potential_capacity_value_brl: float


@dataclass(frozen=True, slots=True)
class PortfolioAnalysis:
    """Cross-lab aggregate used by reports and the mini frontend."""

    labs: tuple[ProductivityAnalysis, ...]
    total_volume: float
    total_manual_human_hours: float
    total_atlas_human_hours: float
    total_human_hours_liberated: float
    human_time_reduction_pct: float
    manual_throughput_per_human_hour: float
    atlas_throughput_per_human_hour: float
    throughput_gain_pct: float
    weighted_automation_rate_pct: float
    weighted_human_intervention_rate_pct: float
    weighted_response_reduction_pct: float | None
    potential_capacity_value_brl: float
    annual_potential_capacity_value_brl: float


@dataclass(frozen=True, slots=True)
class MeasuredRunEvidence:
    """Small non-commercial view of a previously measured technical run."""

    run_id: str
    suite_id: str
    atlas_version: str
    success_rate_pct: float
    weighted_score: float
    evaluated_cases: int
    finished_at_utc: str


class ProductivityEngine:
    """Normalize operational gains without mixing them with measured timings."""

    DISCLAIMER = (
        "Synthetic productivity and economic projection. Operational values are "
        "scenario simulations, monetary values represent potential reusable human "
        "capacity. This is not a guarantee of savings, revenue, staffing change, "
        "conversion, SLA, or customer outcome."
    )

    def analyze(self, snapshot: ProductivitySnapshot) -> ProductivityAnalysis:
        liberated = snapshot.manual_human_hours - snapshot.atlas_human_hours
        reduction = self._reduction_pct(
            snapshot.manual_human_hours,
            snapshot.atlas_human_hours,
        )
        throughput_gain = self._gain_pct(
            snapshot.manual_throughput_per_human_hour,
            snapshot.atlas_throughput_per_human_hour,
        )
        response_reduction = None
        if (
            snapshot.manual_response_minutes is not None
            and snapshot.atlas_response_minutes is not None
        ):
            response_reduction = self._reduction_pct(
                snapshot.manual_response_minutes,
                snapshot.atlas_response_minutes,
            )
        error_reduction = None
        if snapshot.manual_expected_errors > 0:
            error_reduction = self._reduction_pct(
                snapshot.manual_expected_errors,
                snapshot.atlas_expected_errors,
            )

        capacity_value = liberated * snapshot.hourly_cost_brl
        annual_value = capacity_value * self._annual_multiplier(snapshot.period_label)
        return ProductivityAnalysis(
            snapshot=snapshot,
            human_hours_liberated=round(liberated, 3),
            human_time_reduction_pct=round(reduction, 3),
            throughput_gain_pct=round(throughput_gain, 3),
            response_reduction_pct=self._round_optional(response_reduction),
            expected_error_reduction_pct=self._round_optional(error_reduction),
            human_intervention_rate_pct=round(
                100.0 - snapshot.automation_rate_pct,
                3,
            ),
            potential_capacity_value_brl=round(capacity_value, 2),
            annual_potential_capacity_value_brl=round(annual_value, 2),
        )

    def consolidate(
        self,
        snapshots: tuple[ProductivitySnapshot, ...],
    ) -> PortfolioAnalysis:
        if not snapshots:
            raise ValueError("at least one productivity snapshot is required")
        analyses = tuple(self.analyze(snapshot) for snapshot in snapshots)
        total_volume = sum(item.snapshot.volume for item in analyses)
        manual_hours = sum(item.snapshot.manual_human_hours for item in analyses)
        atlas_hours = sum(item.snapshot.atlas_human_hours for item in analyses)
        liberated = manual_hours - atlas_hours
        manual_throughput = self._safe_rate(total_volume, manual_hours)
        atlas_throughput = self._safe_rate(total_volume, atlas_hours)
        weighted_automation = self._weighted_average(
            tuple(
                (item.snapshot.automation_rate_pct, item.snapshot.volume)
                for item in analyses
            )
        )
        response_pairs = tuple(
            (item.response_reduction_pct, item.snapshot.volume)
            for item in analyses
            if item.response_reduction_pct is not None
        )
        weighted_response = (
            self._weighted_average(response_pairs) if response_pairs else None
        )
        capacity_value = sum(item.potential_capacity_value_brl for item in analyses)
        annual_value = sum(
            item.annual_potential_capacity_value_brl for item in analyses
        )
        return PortfolioAnalysis(
            labs=analyses,
            total_volume=round(total_volume, 3),
            total_manual_human_hours=round(manual_hours, 3),
            total_atlas_human_hours=round(atlas_hours, 3),
            total_human_hours_liberated=round(liberated, 3),
            human_time_reduction_pct=round(
                self._reduction_pct(manual_hours, atlas_hours),
                3,
            ),
            manual_throughput_per_human_hour=round(manual_throughput, 3),
            atlas_throughput_per_human_hour=round(atlas_throughput, 3),
            throughput_gain_pct=round(
                self._gain_pct(manual_throughput, atlas_throughput),
                3,
            ),
            weighted_automation_rate_pct=round(weighted_automation, 3),
            weighted_human_intervention_rate_pct=round(
                100.0 - weighted_automation,
                3,
            ),
            weighted_response_reduction_pct=self._round_optional(
                weighted_response
            ),
            potential_capacity_value_brl=round(capacity_value, 2),
            annual_potential_capacity_value_brl=round(annual_value, 2),
        )

    @staticmethod
    def _reduction_pct(baseline: float, assisted: float) -> float:
        if baseline <= 0:
            return 0.0
        return (baseline - assisted) / baseline * 100.0

    @staticmethod
    def _gain_pct(baseline: float, assisted: float) -> float:
        if baseline <= 0:
            return 0.0
        return (assisted - baseline) / baseline * 100.0

    @staticmethod
    def _safe_rate(items: float, hours: float) -> float:
        return items / hours if hours > 0 else 0.0

    @staticmethod
    def _weighted_average(values: tuple[tuple[float, float], ...]) -> float:
        total_weight = sum(weight for _, weight in values)
        if total_weight <= 0:
            return 0.0
        return sum(value * weight for value, weight in values) / total_weight

    @staticmethod
    def _annual_multiplier(period_label: str) -> float:
        normalized = period_label.strip().lower()
        return {
            "month": 12.0,
            "monthly": 12.0,
            "week": 52.0,
            "weekly": 52.0,
            "day": 365.0,
            "daily": 365.0,
            "year": 1.0,
            "yearly": 1.0,
            "annual": 1.0,
        }.get(normalized, 12.0)

    @staticmethod
    def _round_optional(value: float | None) -> float | None:
        return None if value is None else round(value, 3)


def school_snapshot(result: SchoolLeadSimulationResult) -> ProductivitySnapshot:
    scenario = result.scenario
    business = result.business
    return ProductivitySnapshot(
        lab_id="school",
        title=scenario.title,
        period_label=scenario.period_label,
        volume=float(scenario.leads_per_period),
        automation_rate_pct=scenario.automation_rate_pct,
        hourly_cost_brl=scenario.hourly_cost_brl,
        manual_human_hours=business.manual_human_hours,
        atlas_human_hours=business.atlas_human_hours,
        manual_throughput_per_human_hour=result.manual_leads_per_human_hour,
        atlas_throughput_per_human_hour=result.atlas_leads_per_human_hour,
        manual_expected_errors=business.manual_expected_errors,
        atlas_expected_errors=business.atlas_expected_errors,
        manual_response_minutes=result.manual_avg_first_response_minutes,
        atlas_response_minutes=result.atlas_avg_first_response_minutes,
    )


def helpdesk_snapshot(result: HelpDeskSimulationResult) -> ProductivitySnapshot:
    scenario = result.scenario
    total_operations = float(
        scenario.tickets_per_period + scenario.onboardings_per_period
    )
    automated_operations = (
        scenario.tickets_per_period * scenario.automation_rate_pct / 100.0
        + scenario.onboardings_per_period
        * scenario.provisioning_automation_rate_pct
        / 100.0
    )
    automation_rate = (
        automated_operations / total_operations * 100.0
        if total_operations > 0
        else 0.0
    )
    return ProductivitySnapshot(
        lab_id="helpdesk",
        title=scenario.title,
        period_label=scenario.period_label,
        volume=total_operations,
        automation_rate_pct=automation_rate,
        hourly_cost_brl=scenario.hourly_cost_brl,
        manual_human_hours=result.total_manual_human_hours,
        atlas_human_hours=result.total_atlas_human_hours,
        manual_throughput_per_human_hour=result.manual_operations_per_human_hour,
        atlas_throughput_per_human_hour=result.atlas_operations_per_human_hour,
        manual_expected_errors=result.ticket_business.manual_expected_errors,
        atlas_expected_errors=result.ticket_business.atlas_expected_errors,
        manual_response_minutes=result.manual_avg_first_response_minutes,
        atlas_response_minutes=result.atlas_avg_first_response_minutes,
    )


def retail_snapshot(result: RetailSimulationResult) -> ProductivitySnapshot:
    scenario = result.scenario
    business = result.business
    return ProductivitySnapshot(
        lab_id="retail",
        title=scenario.title,
        period_label=scenario.period_label,
        volume=float(scenario.operations_per_period),
        automation_rate_pct=scenario.automation_rate_pct,
        hourly_cost_brl=scenario.hourly_cost_brl,
        manual_human_hours=business.manual_human_hours,
        atlas_human_hours=business.atlas_human_hours,
        manual_throughput_per_human_hour=result.manual_operations_per_human_hour,
        atlas_throughput_per_human_hour=result.atlas_operations_per_human_hour,
        manual_expected_errors=business.manual_expected_errors,
        atlas_expected_errors=business.atlas_expected_errors,
        manual_response_minutes=result.manual_avg_exception_response_minutes,
        atlas_response_minutes=result.atlas_avg_exception_response_minutes,
    )


def office_snapshot(result: OfficeSimulationResult) -> ProductivitySnapshot:
    scenario = result.scenario
    business = result.business
    return ProductivitySnapshot(
        lab_id="office",
        title=scenario.title,
        period_label=scenario.period_label,
        volume=float(scenario.tasks_per_period),
        automation_rate_pct=scenario.automation_rate_pct,
        hourly_cost_brl=scenario.hourly_cost_brl,
        manual_human_hours=business.manual_human_hours,
        atlas_human_hours=business.atlas_human_hours,
        manual_throughput_per_human_hour=result.manual_tasks_per_human_hour,
        atlas_throughput_per_human_hour=result.atlas_tasks_per_human_hour,
        manual_expected_errors=business.manual_expected_errors,
        atlas_expected_errors=business.atlas_expected_errors,
        manual_response_minutes=result.manual_avg_first_action_minutes,
        atlas_response_minutes=result.atlas_avg_first_action_minutes,
    )


def collect_measured_run_evidence(
    root: Path,
    *,
    max_runs: int = 8,
) -> tuple[MeasuredRunEvidence, ...]:
    """Read recent technical benchmark history without using it as ROI input."""

    if max_runs <= 0:
        return ()
    store = BenchmarkRunStore(Path(root))
    collected: list[MeasuredRunEvidence] = []
    for run_id in reversed(store.list_run_ids()):
        try:
            run = store.load(run_id)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if run.kind is not BenchmarkKind.TECHNICAL:
            continue
        collected.append(
            MeasuredRunEvidence(
                run_id=run.run_id,
                suite_id=run.suite_id,
                atlas_version=run.atlas_version,
                success_rate_pct=run.summary.success_rate,
                weighted_score=run.summary.weighted_score,
                evaluated_cases=run.summary.evaluated,
                finished_at_utc=run.finished_at_utc,
            )
        )
        if len(collected) >= max_runs:
            break
    return tuple(collected)


def portfolio_dashboard_payload(
    portfolio: PortfolioAnalysis,
    *,
    measured_runs: tuple[MeasuredRunEvidence, ...] = (),
) -> dict[str, object]:
    """Stable frontend-ready contract with explicit provenance sections."""

    labs = []
    for analysis in portfolio.labs:
        snapshot = analysis.snapshot
        labs.append(
            {
                "lab_id": snapshot.lab_id,
                "title": snapshot.title,
                "period": snapshot.period_label,
                "volume": snapshot.volume,
                "simulated": {
                    "automation_rate_pct": snapshot.automation_rate_pct,
                    "human_intervention_rate_pct": (
                        analysis.human_intervention_rate_pct
                    ),
                    "manual_human_hours": snapshot.manual_human_hours,
                    "atlas_human_hours": snapshot.atlas_human_hours,
                    "human_hours_liberated": analysis.human_hours_liberated,
                    "human_time_reduction_pct": analysis.human_time_reduction_pct,
                    "manual_throughput_per_human_hour": (
                        snapshot.manual_throughput_per_human_hour
                    ),
                    "atlas_throughput_per_human_hour": (
                        snapshot.atlas_throughput_per_human_hour
                    ),
                    "throughput_gain_pct": analysis.throughput_gain_pct,
                    "response_reduction_pct": analysis.response_reduction_pct,
                    "expected_error_reduction_pct": (
                        analysis.expected_error_reduction_pct
                    ),
                },
                "economic_projection": {
                    "hourly_cost_brl": snapshot.hourly_cost_brl,
                    "potential_capacity_value_brl": (
                        analysis.potential_capacity_value_brl
                    ),
                    "annual_potential_capacity_value_brl": (
                        analysis.annual_potential_capacity_value_brl
                    ),
                },
            }
        )

    return {
        "schema_version": "1.0",
        "kind": "roi_productivity_portfolio",
        "portfolio": {
            "lab_count": len(portfolio.labs),
            "total_volume": portfolio.total_volume,
            "total_manual_human_hours": portfolio.total_manual_human_hours,
            "total_atlas_human_hours": portfolio.total_atlas_human_hours,
            "total_human_hours_liberated": portfolio.total_human_hours_liberated,
            "human_time_reduction_pct": portfolio.human_time_reduction_pct,
            "manual_throughput_per_human_hour": (
                portfolio.manual_throughput_per_human_hour
            ),
            "atlas_throughput_per_human_hour": (
                portfolio.atlas_throughput_per_human_hour
            ),
            "throughput_gain_pct": portfolio.throughput_gain_pct,
            "weighted_automation_rate_pct": (
                portfolio.weighted_automation_rate_pct
            ),
            "weighted_human_intervention_rate_pct": (
                portfolio.weighted_human_intervention_rate_pct
            ),
            "weighted_response_reduction_pct": (
                portfolio.weighted_response_reduction_pct
            ),
        },
        "labs": labs,
        "evidence": {
            EvidenceKind.MEASURED.value: {
                "available": bool(measured_runs),
                "used_in_roi": False,
                "description": (
                    "Measured technical benchmark history is shown separately "
                    "and is not converted into commercial ROI."
                ),
                "runs": [
                    {
                        "run_id": item.run_id,
                        "suite_id": item.suite_id,
                        "atlas_version": item.atlas_version,
                        "success_rate_pct": item.success_rate_pct,
                        "weighted_score": item.weighted_score,
                        "evaluated_cases": item.evaluated_cases,
                        "finished_at_utc": item.finished_at_utc,
                    }
                    for item in measured_runs
                ],
            },
            EvidenceKind.SIMULATED.value: {
                "available": True,
                "used_in_roi": True,
                "description": (
                    "Operational workload values come from explicit synthetic "
                    "School, Help Desk, Retail and Office scenarios."
                ),
            },
            EvidenceKind.ECONOMIC_PROJECTION.value: {
                "available": True,
                "used_in_roi": True,
                "potential_capacity_value_brl": (
                    portfolio.potential_capacity_value_brl
                ),
                "annual_potential_capacity_value_brl": (
                    portfolio.annual_potential_capacity_value_brl
                ),
                "description": (
                    "Potential capacity value equals simulated human hours "
                    "liberated multiplied by each scenario hourly cost."
                ),
            },
        },
        "frontend": {
            "ready": True,
            "view": "portfolio_overview",
            "tabs": ["overview", "school", "helpdesk", "retail", "office"],
            "primary_cards": [
                "human_hours_liberated",
                "human_time_reduction_pct",
                "throughput_gain_pct",
                "potential_capacity_value_brl",
            ],
        },
        "disclaimer": ProductivityEngine.DISCLAIMER,
    }
