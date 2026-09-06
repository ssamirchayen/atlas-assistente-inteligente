"""Deterministic business simulation engine for Sprint 27 stage 7.

The engine uses explicit synthetic assumptions and expected-value arithmetic.
It does not claim measured customer savings. Later business labs can replace
Atlas timing assumptions with measured benchmark observations while preserving
the same result contract.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class BusinessScenario:
    """Transparent assumptions for one operational process simulation."""

    scenario_id: str
    title: str
    volume_per_period: int
    staff_count: int
    work_hours_per_staff: float
    hourly_cost_brl: float
    manual_minutes_per_item: float
    atlas_seconds_per_automated_item: float
    automation_rate_pct: float
    human_review_minutes_per_automated_item: float = 0.0
    manual_error_rate_pct: float = 0.0
    atlas_error_rate_pct: float = 0.0
    rework_minutes_per_error: float = 0.0
    period_label: str = "month"
    atlas_time_source: str = "synthetic_assumption"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if self.volume_per_period < 0:
            raise ValueError("volume_per_period cannot be negative")
        if self.staff_count <= 0:
            raise ValueError("staff_count must be positive")
        if self.work_hours_per_staff <= 0:
            raise ValueError("work_hours_per_staff must be positive")
        if self.hourly_cost_brl < 0:
            raise ValueError("hourly_cost_brl cannot be negative")
        if self.manual_minutes_per_item <= 0:
            raise ValueError("manual_minutes_per_item must be positive")
        if self.atlas_seconds_per_automated_item < 0:
            raise ValueError("atlas_seconds_per_automated_item cannot be negative")
        if self.human_review_minutes_per_automated_item < 0:
            raise ValueError(
                "human_review_minutes_per_automated_item cannot be negative"
            )
        if self.rework_minutes_per_error < 0:
            raise ValueError("rework_minutes_per_error cannot be negative")
        for name in (
            "automation_rate_pct",
            "manual_error_rate_pct",
            "atlas_error_rate_pct",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be between 0 and 100")
        if not self.period_label.strip():
            raise ValueError("period_label cannot be empty")
        if not self.atlas_time_source.strip():
            raise ValueError("atlas_time_source cannot be empty")

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "BusinessScenario":
        """Build a scenario from a benchmark case parameter mapping."""

        return cls(
            scenario_id=str(payload.get("scenario_id", "business.synthetic")),
            title=str(payload.get("title", "Synthetic business scenario")),
            volume_per_period=int(payload.get("volume_per_period", 1000)),
            staff_count=int(payload.get("staff_count", 5)),
            work_hours_per_staff=float(payload.get("work_hours_per_staff", 176.0)),
            hourly_cost_brl=float(payload.get("hourly_cost_brl", 20.0)),
            manual_minutes_per_item=float(
                payload.get("manual_minutes_per_item", 6.0)
            ),
            atlas_seconds_per_automated_item=float(
                payload.get("atlas_seconds_per_automated_item", 15.0)
            ),
            automation_rate_pct=float(payload.get("automation_rate_pct", 75.0)),
            human_review_minutes_per_automated_item=float(
                payload.get("human_review_minutes_per_automated_item", 0.5)
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

    def with_volume(self, volume: int) -> "BusinessScenario":
        """Return the same assumptions at a different deterministic volume."""

        return replace(self, volume_per_period=int(volume))


@dataclass(frozen=True, slots=True)
class BusinessSimulationResult:
    """Expected-value comparison between manual and Atlas-assisted operation."""

    scenario: BusinessScenario
    automated_items: float
    manual_items_remaining: float
    manual_expected_errors: float
    atlas_expected_errors: float
    manual_rework_hours: float
    atlas_rework_hours: float
    manual_human_hours: float
    atlas_human_hours: float
    atlas_machine_hours: float
    available_human_hours: float
    human_hours_liberated: float
    human_time_reduction_pct: float
    manual_utilization_pct: float
    atlas_human_utilization_pct: float
    manual_capacity_items: float
    atlas_capacity_items: float
    capacity_gain_pct: float
    potential_capacity_value_brl: float
    annual_potential_capacity_value_brl: float


class BusinessSimulationEngine:
    """Pure calculator shared by all synthetic business labs."""

    DISCLAIMER = (
        "Synthetic simulation: values are scenario projections, not guaranteed "
        "customer savings or commercial outcomes."
    )

    def simulate(self, scenario: BusinessScenario) -> BusinessSimulationResult:
        volume = float(scenario.volume_per_period)
        automation_rate = scenario.automation_rate_pct / 100.0
        automated_items = volume * automation_rate
        manual_items_remaining = volume - automated_items

        manual_expected_errors = volume * scenario.manual_error_rate_pct / 100.0
        atlas_expected_errors = (
            automated_items * scenario.atlas_error_rate_pct / 100.0
            + manual_items_remaining * scenario.manual_error_rate_pct / 100.0
        )

        manual_rework_hours = (
            manual_expected_errors * scenario.rework_minutes_per_error / 60.0
        )
        atlas_rework_hours = (
            atlas_expected_errors * scenario.rework_minutes_per_error / 60.0
        )

        manual_human_hours = (
            volume * scenario.manual_minutes_per_item / 60.0 + manual_rework_hours
        )
        atlas_human_hours = (
            manual_items_remaining * scenario.manual_minutes_per_item / 60.0
            + automated_items
            * scenario.human_review_minutes_per_automated_item
            / 60.0
            + atlas_rework_hours
        )
        atlas_machine_hours = (
            automated_items * scenario.atlas_seconds_per_automated_item / 3600.0
        )
        available_human_hours = (
            scenario.staff_count * scenario.work_hours_per_staff
        )

        human_hours_liberated = manual_human_hours - atlas_human_hours
        human_time_reduction_pct = self._reduction_pct(
            manual_human_hours,
            atlas_human_hours,
        )

        manual_utilization_pct = self._ratio_pct(
            manual_human_hours,
            available_human_hours,
        )
        atlas_human_utilization_pct = self._ratio_pct(
            atlas_human_hours,
            available_human_hours,
        )

        manual_human_minutes_per_item = self._per_item_minutes(
            manual_human_hours,
            volume,
        )
        atlas_human_minutes_per_item = self._per_item_minutes(
            atlas_human_hours,
            volume,
        )
        manual_capacity_items = self._capacity_items(
            available_human_hours,
            manual_human_minutes_per_item,
        )
        atlas_capacity_items = self._capacity_items(
            available_human_hours,
            atlas_human_minutes_per_item,
        )
        capacity_gain_pct = self._gain_pct(
            manual_capacity_items,
            atlas_capacity_items,
        )

        potential_capacity_value_brl = (
            human_hours_liberated * scenario.hourly_cost_brl
        )

        return BusinessSimulationResult(
            scenario=scenario,
            automated_items=round(automated_items, 3),
            manual_items_remaining=round(manual_items_remaining, 3),
            manual_expected_errors=round(manual_expected_errors, 3),
            atlas_expected_errors=round(atlas_expected_errors, 3),
            manual_rework_hours=round(manual_rework_hours, 3),
            atlas_rework_hours=round(atlas_rework_hours, 3),
            manual_human_hours=round(manual_human_hours, 3),
            atlas_human_hours=round(atlas_human_hours, 3),
            atlas_machine_hours=round(atlas_machine_hours, 3),
            available_human_hours=round(available_human_hours, 3),
            human_hours_liberated=round(human_hours_liberated, 3),
            human_time_reduction_pct=round(human_time_reduction_pct, 3),
            manual_utilization_pct=round(manual_utilization_pct, 3),
            atlas_human_utilization_pct=round(atlas_human_utilization_pct, 3),
            manual_capacity_items=round(manual_capacity_items, 3),
            atlas_capacity_items=round(atlas_capacity_items, 3),
            capacity_gain_pct=round(capacity_gain_pct, 3),
            potential_capacity_value_brl=round(potential_capacity_value_brl, 2),
            annual_potential_capacity_value_brl=round(
                potential_capacity_value_brl * 12.0,
                2,
            ),
        )

    @staticmethod
    def _ratio_pct(numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return numerator / denominator * 100.0

    @staticmethod
    def _reduction_pct(baseline: float, current: float) -> float:
        if baseline <= 0:
            return 0.0
        return (baseline - current) / baseline * 100.0

    @staticmethod
    def _gain_pct(baseline: float, current: float) -> float:
        if baseline <= 0:
            return 0.0
        return (current / baseline - 1.0) * 100.0

    @staticmethod
    def _per_item_minutes(hours: float, volume: float) -> float:
        if volume <= 0:
            return 0.0
        return hours * 60.0 / volume

    @staticmethod
    def _capacity_items(
        available_human_hours: float,
        human_minutes_per_item: float,
    ) -> float:
        if human_minutes_per_item <= 0:
            return 0.0
        return available_human_hours * 60.0 / human_minutes_per_item
