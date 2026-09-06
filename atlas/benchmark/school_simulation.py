"""Synthetic school lead operations simulator for Sprint 27 stage 8.

The simulator compares a transparent manual baseline with an Atlas-assisted
workflow. All commercial inputs are explicit assumptions. Results describe
operational capacity and expected-value workload only; they do not guarantee
sales, enrollment, revenue, or customer savings.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .business_simulation import (
    BusinessScenario,
    BusinessSimulationEngine,
    BusinessSimulationResult,
)


@dataclass(frozen=True, slots=True)
class SyntheticSchoolLead:
    """One deterministic synthetic lead used by the School Lab."""

    lead_id: str
    course: str
    source: str
    interest: str
    after_hours: bool
    message: str


@dataclass(frozen=True, slots=True)
class SchoolLeadScenario:
    """Explicit assumptions for a synthetic school lead operation."""

    scenario_id: str
    title: str
    leads_per_period: int
    consultant_count: int
    work_hours_per_consultant: float
    hourly_cost_brl: float
    courses: tuple[str, ...]
    sources: tuple[str, ...]
    after_hours_lead_pct: float
    automation_rate_pct: float
    manual_first_response_business_minutes: float
    manual_after_hours_wait_minutes: float
    atlas_first_response_seconds: float
    manual_response_handling_minutes: float
    manual_qualification_minutes: float
    manual_crm_minutes: float
    followups_per_lead: int
    manual_followup_minutes: float
    manual_followup_coverage_pct: float
    atlas_followup_coverage_pct: float
    atlas_processing_seconds_per_automated_lead: float
    human_review_minutes_per_automated_lead: float
    manual_error_rate_pct: float
    atlas_error_rate_pct: float
    rework_minutes_per_error: float
    period_label: str = "month"
    atlas_time_source: str = "synthetic_assumption"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if self.leads_per_period <= 0:
            raise ValueError("leads_per_period must be positive")
        if self.consultant_count <= 0:
            raise ValueError("consultant_count must be positive")
        if self.work_hours_per_consultant <= 0:
            raise ValueError("work_hours_per_consultant must be positive")
        if self.hourly_cost_brl < 0:
            raise ValueError("hourly_cost_brl cannot be negative")
        if not self.courses:
            raise ValueError("courses cannot be empty")
        if not self.sources:
            raise ValueError("sources cannot be empty")
        if self.followups_per_lead < 0:
            raise ValueError("followups_per_lead cannot be negative")
        for name in (
            "after_hours_lead_pct",
            "automation_rate_pct",
            "manual_followup_coverage_pct",
            "atlas_followup_coverage_pct",
            "manual_error_rate_pct",
            "atlas_error_rate_pct",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be between 0 and 100")
        for name in (
            "manual_first_response_business_minutes",
            "manual_after_hours_wait_minutes",
            "atlas_first_response_seconds",
            "manual_response_handling_minutes",
            "manual_qualification_minutes",
            "manual_crm_minutes",
            "manual_followup_minutes",
            "atlas_processing_seconds_per_automated_lead",
            "human_review_minutes_per_automated_lead",
            "rework_minutes_per_error",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        if not self.period_label.strip():
            raise ValueError("period_label cannot be empty")
        if not self.atlas_time_source.strip():
            raise ValueError("atlas_time_source cannot be empty")

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SchoolLeadScenario":
        courses = payload.get(
            "courses",
            [
                "Radiologia",
                "Enfermagem",
                "Administracao",
                "Eletrotecnica",
                "Informatica",
                "Logistica",
                "Seguranca do Trabalho",
                "Recursos Humanos",
            ],
        )
        sources = payload.get(
            "sources",
            ["Instagram", "WhatsApp", "Site", "Indicacao"],
        )
        if not isinstance(courses, (list, tuple)):
            raise ValueError("courses must be a list")
        if not isinstance(sources, (list, tuple)):
            raise ValueError("sources must be a list")

        return cls(
            scenario_id=str(payload.get("scenario_id", "school.leads")),
            title=str(payload.get("title", "Synthetic School Lead Simulation")),
            leads_per_period=int(payload.get("leads_per_period", 2000)),
            consultant_count=int(payload.get("consultant_count", 5)),
            work_hours_per_consultant=float(
                payload.get("work_hours_per_consultant", 176.0)
            ),
            hourly_cost_brl=float(payload.get("hourly_cost_brl", 20.0)),
            courses=tuple(str(item) for item in courses),
            sources=tuple(str(item) for item in sources),
            after_hours_lead_pct=float(payload.get("after_hours_lead_pct", 30.0)),
            automation_rate_pct=float(payload.get("automation_rate_pct", 80.0)),
            manual_first_response_business_minutes=float(
                payload.get("manual_first_response_business_minutes", 35.0)
            ),
            manual_after_hours_wait_minutes=float(
                payload.get("manual_after_hours_wait_minutes", 600.0)
            ),
            atlas_first_response_seconds=float(
                payload.get("atlas_first_response_seconds", 8.0)
            ),
            manual_response_handling_minutes=float(
                payload.get("manual_response_handling_minutes", 2.0)
            ),
            manual_qualification_minutes=float(
                payload.get("manual_qualification_minutes", 3.0)
            ),
            manual_crm_minutes=float(payload.get("manual_crm_minutes", 2.0)),
            followups_per_lead=int(payload.get("followups_per_lead", 2)),
            manual_followup_minutes=float(
                payload.get("manual_followup_minutes", 2.0)
            ),
            manual_followup_coverage_pct=float(
                payload.get("manual_followup_coverage_pct", 65.0)
            ),
            atlas_followup_coverage_pct=float(
                payload.get("atlas_followup_coverage_pct", 98.0)
            ),
            atlas_processing_seconds_per_automated_lead=float(
                payload.get("atlas_processing_seconds_per_automated_lead", 18.0)
            ),
            human_review_minutes_per_automated_lead=float(
                payload.get("human_review_minutes_per_automated_lead", 0.5)
            ),
            manual_error_rate_pct=float(
                payload.get("manual_error_rate_pct", 4.0)
            ),
            atlas_error_rate_pct=float(payload.get("atlas_error_rate_pct", 1.0)),
            rework_minutes_per_error=float(
                payload.get("rework_minutes_per_error", 5.0)
            ),
            period_label=str(payload.get("period_label", "month")),
            atlas_time_source=str(
                payload.get("atlas_time_source", "synthetic_assumption")
            ),
        )

    @property
    def manual_minutes_per_lead(self) -> float:
        followup_minutes = (
            self.followups_per_lead
            * self.manual_followup_minutes
            * self.manual_followup_coverage_pct
            / 100.0
        )
        return (
            self.manual_response_handling_minutes
            + self.manual_qualification_minutes
            + self.manual_crm_minutes
            + followup_minutes
        )

    def to_business_scenario(self) -> BusinessScenario:
        """Translate School Lab assumptions into the generic business engine."""

        return BusinessScenario(
            scenario_id=self.scenario_id,
            title=self.title,
            volume_per_period=self.leads_per_period,
            staff_count=self.consultant_count,
            work_hours_per_staff=self.work_hours_per_consultant,
            hourly_cost_brl=self.hourly_cost_brl,
            manual_minutes_per_item=self.manual_minutes_per_lead,
            atlas_seconds_per_automated_item=(
                self.atlas_processing_seconds_per_automated_lead
            ),
            automation_rate_pct=self.automation_rate_pct,
            human_review_minutes_per_automated_item=(
                self.human_review_minutes_per_automated_lead
            ),
            manual_error_rate_pct=self.manual_error_rate_pct,
            atlas_error_rate_pct=self.atlas_error_rate_pct,
            rework_minutes_per_error=self.rework_minutes_per_error,
            period_label=self.period_label,
            atlas_time_source=self.atlas_time_source,
        )


@dataclass(frozen=True, slots=True)
class SchoolLeadSimulationResult:
    """School-specific operational metrics plus generic workload economics."""

    scenario: SchoolLeadScenario
    business: BusinessSimulationResult
    after_hours_leads: float
    manual_avg_first_response_minutes: float
    atlas_avg_first_response_minutes: float
    first_response_reduction_pct: float
    manual_followups_completed: float
    atlas_followups_completed: float
    manual_followup_coverage_pct: float
    atlas_followup_coverage_pct: float
    manual_leads_per_human_hour: float
    atlas_leads_per_human_hour: float


class SchoolLeadSimulationEngine:
    """Deterministic expected-value simulator for school lead operations."""

    DISCLAIMER = (
        "Synthetic School Lab projection. It estimates operational workload and "
        "capacity only; it does not guarantee enrollments, conversion, revenue, "
        "savings, or real customer outcomes."
    )

    def simulate(self, scenario: SchoolLeadScenario) -> SchoolLeadSimulationResult:
        business = BusinessSimulationEngine().simulate(
            scenario.to_business_scenario()
        )
        volume = float(scenario.leads_per_period)
        after_hours_rate = scenario.after_hours_lead_pct / 100.0
        automation_rate = scenario.automation_rate_pct / 100.0

        after_hours_leads = volume * after_hours_rate
        manual_avg_first_response_minutes = (
            (1.0 - after_hours_rate)
            * scenario.manual_first_response_business_minutes
            + after_hours_rate * scenario.manual_after_hours_wait_minutes
        )
        atlas_automated_response_minutes = (
            scenario.atlas_first_response_seconds / 60.0
        )
        atlas_avg_first_response_minutes = (
            automation_rate * atlas_automated_response_minutes
            + (1.0 - automation_rate) * manual_avg_first_response_minutes
        )
        first_response_reduction_pct = self._reduction_pct(
            manual_avg_first_response_minutes,
            atlas_avg_first_response_minutes,
        )

        possible_followups = volume * scenario.followups_per_lead
        manual_followups_completed = (
            possible_followups * scenario.manual_followup_coverage_pct / 100.0
        )
        automated_followups = (
            possible_followups
            * automation_rate
            * scenario.atlas_followup_coverage_pct
            / 100.0
        )
        remaining_manual_followups = (
            possible_followups
            * (1.0 - automation_rate)
            * scenario.manual_followup_coverage_pct
            / 100.0
        )
        atlas_followups_completed = automated_followups + remaining_manual_followups
        atlas_followup_coverage_pct = self._ratio_pct(
            atlas_followups_completed,
            possible_followups,
        )

        return SchoolLeadSimulationResult(
            scenario=scenario,
            business=business,
            after_hours_leads=round(after_hours_leads, 3),
            manual_avg_first_response_minutes=round(
                manual_avg_first_response_minutes,
                3,
            ),
            atlas_avg_first_response_minutes=round(
                atlas_avg_first_response_minutes,
                3,
            ),
            first_response_reduction_pct=round(
                first_response_reduction_pct,
                3,
            ),
            manual_followups_completed=round(manual_followups_completed, 3),
            atlas_followups_completed=round(atlas_followups_completed, 3),
            manual_followup_coverage_pct=round(
                scenario.manual_followup_coverage_pct,
                3,
            ),
            atlas_followup_coverage_pct=round(
                atlas_followup_coverage_pct,
                3,
            ),
            manual_leads_per_human_hour=round(
                self._safe_rate(volume, business.manual_human_hours),
                3,
            ),
            atlas_leads_per_human_hour=round(
                self._safe_rate(volume, business.atlas_human_hours),
                3,
            ),
        )

    @staticmethod
    def generate_leads(
        scenario: SchoolLeadScenario,
        *,
        seed: int,
        count: int | None = None,
    ) -> tuple[SyntheticSchoolLead, ...]:
        """Generate deterministic, privacy-safe synthetic leads."""

        total = scenario.leads_per_period if count is None else int(count)
        if total < 0:
            raise ValueError("count cannot be negative")
        rng = random.Random(int(seed))
        interests = ("low", "medium", "high")
        templates = (
            "Quero saber o valor do curso de {course}.",
            "Quando comeca a proxima turma de {course}?",
            "Tenho interesse em {course}; como faco a matricula?",
            "Quais sao os horarios do curso de {course}?",
        )
        leads: list[SyntheticSchoolLead] = []
        after_hours_probability = scenario.after_hours_lead_pct / 100.0

        for index in range(total):
            course = rng.choice(scenario.courses)
            source = rng.choice(scenario.sources)
            interest = rng.choice(interests)
            after_hours = rng.random() < after_hours_probability
            message = rng.choice(templates).format(course=course)
            leads.append(
                SyntheticSchoolLead(
                    lead_id=f"SIM-{index + 1:06d}",
                    course=course,
                    source=source,
                    interest=interest,
                    after_hours=after_hours,
                    message=message,
                )
            )
        return tuple(leads)

    @staticmethod
    def _reduction_pct(baseline: float, assisted: float) -> float:
        if baseline <= 0:
            return 0.0
        return (baseline - assisted) / baseline * 100.0

    @staticmethod
    def _ratio_pct(part: float, whole: float) -> float:
        if whole <= 0:
            return 0.0
        return part / whole * 100.0

    @staticmethod
    def _safe_rate(items: float, hours: float) -> float:
        if hours <= 0:
            return 0.0
        return items / hours


def school_dashboard_payload(result: SchoolLeadSimulationResult) -> dict[str, object]:
    """Stable JSON-safe payload reserved for the mini benchmark frontend."""

    scenario = result.scenario
    business = result.business
    return {
        "schema_version": "1.0",
        "kind": "school_lead_simulation",
        "scenario": {
            "id": scenario.scenario_id,
            "title": scenario.title,
            "period": scenario.period_label,
            "leads": scenario.leads_per_period,
            "consultants": scenario.consultant_count,
            "courses": list(scenario.courses),
            "sources": list(scenario.sources),
            "atlas_time_source": scenario.atlas_time_source,
        },
        "lead_mix": {
            "after_hours_pct": scenario.after_hours_lead_pct,
            "after_hours_leads": result.after_hours_leads,
            "automation_rate_pct": scenario.automation_rate_pct,
        },
        "response": {
            "manual_avg_first_response_minutes": (
                result.manual_avg_first_response_minutes
            ),
            "atlas_avg_first_response_minutes": (
                result.atlas_avg_first_response_minutes
            ),
            "first_response_reduction_pct": result.first_response_reduction_pct,
        },
        "followups": {
            "per_lead": scenario.followups_per_lead,
            "manual_completed": result.manual_followups_completed,
            "atlas_completed": result.atlas_followups_completed,
            "manual_coverage_pct": result.manual_followup_coverage_pct,
            "atlas_coverage_pct": result.atlas_followup_coverage_pct,
        },
        "workload": {
            "manual_human_hours": business.manual_human_hours,
            "atlas_human_hours": business.atlas_human_hours,
            "atlas_machine_hours": business.atlas_machine_hours,
            "human_hours_liberated": business.human_hours_liberated,
            "human_time_reduction_pct": business.human_time_reduction_pct,
            "manual_leads_per_human_hour": result.manual_leads_per_human_hour,
            "atlas_leads_per_human_hour": result.atlas_leads_per_human_hour,
            "capacity_gain_pct": business.capacity_gain_pct,
        },
        "quality": {
            "manual_expected_errors": business.manual_expected_errors,
            "atlas_expected_errors": business.atlas_expected_errors,
            "conversion_modeled": False,
        },
        "economics": {
            "potential_capacity_value_brl": business.potential_capacity_value_brl,
            "annual_potential_capacity_value_brl": (
                business.annual_potential_capacity_value_brl
            ),
        },
        "frontend": {
            "recommended_cards": [
                "leads",
                "first_response",
                "followup_coverage",
                "human_hours_liberated",
                "capacity_gain",
            ],
            "recommended_comparison": "manual_vs_atlas",
        },
        "disclaimer": SchoolLeadSimulationEngine.DISCLAIMER,
    }
