"""Synthetic Retail + Office simulators for Sprint 27 stage 10.

Both labs use explicit deterministic assumptions and expected-value arithmetic.
They estimate operational workload only and do not claim measured customer
savings, revenue, staffing reduction, or guaranteed service outcomes.
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
class SyntheticRetailEvent:
    event_id: str
    category: str
    priority: str
    message: str


@dataclass(frozen=True, slots=True)
class RetailScenario:
    scenario_id: str
    title: str
    operations_per_period: int
    staff_count: int
    work_hours_per_staff: float
    hourly_cost_brl: float
    categories: tuple[str, ...]
    automation_rate_pct: float
    manual_minutes_per_operation: float
    atlas_seconds_per_automated_operation: float
    human_review_minutes_per_automated_operation: float
    manual_error_rate_pct: float
    atlas_error_rate_pct: float
    rework_minutes_per_error: float
    manual_exception_minutes: float
    atlas_exception_seconds: float
    high_priority_pct: float
    period_label: str = "month"
    atlas_time_source: str = "synthetic_assumption"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.title.strip():
            raise ValueError("scenario_id and title cannot be empty")
        if self.operations_per_period <= 0:
            raise ValueError("operations_per_period must be positive")
        if self.staff_count <= 0 or self.work_hours_per_staff <= 0:
            raise ValueError("staff capacity must be positive")
        if self.hourly_cost_brl < 0:
            raise ValueError("hourly_cost_brl cannot be negative")
        if not self.categories:
            raise ValueError("categories cannot be empty")
        for name in (
            "automation_rate_pct",
            "manual_error_rate_pct",
            "atlas_error_rate_pct",
            "high_priority_pct",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be between 0 and 100")
        for name in (
            "manual_minutes_per_operation",
            "atlas_seconds_per_automated_operation",
            "human_review_minutes_per_automated_operation",
            "rework_minutes_per_error",
            "manual_exception_minutes",
            "atlas_exception_seconds",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RetailScenario":
        raw_categories = payload.get(
            "categories",
            ("stock_check", "price_divergence", "supplier_order", "sales_report"),
        )
        if not isinstance(raw_categories, (list, tuple)):
            raise ValueError("categories must be a list or tuple")
        return cls(
            scenario_id=str(payload.get("scenario_id", "retail.synthetic")),
            title=str(payload.get("title", "Synthetic Retail Operations")),
            operations_per_period=int(payload.get("operations_per_period", 3000)),
            staff_count=int(payload.get("staff_count", 6)),
            work_hours_per_staff=float(payload.get("work_hours_per_staff", 176.0)),
            hourly_cost_brl=float(payload.get("hourly_cost_brl", 22.0)),
            categories=tuple(str(item) for item in raw_categories),
            automation_rate_pct=float(payload.get("automation_rate_pct", 68.0)),
            manual_minutes_per_operation=float(
                payload.get("manual_minutes_per_operation", 4.5)
            ),
            atlas_seconds_per_automated_operation=float(
                payload.get("atlas_seconds_per_automated_operation", 20.0)
            ),
            human_review_minutes_per_automated_operation=float(
                payload.get("human_review_minutes_per_automated_operation", 0.8)
            ),
            manual_error_rate_pct=float(payload.get("manual_error_rate_pct", 4.5)),
            atlas_error_rate_pct=float(payload.get("atlas_error_rate_pct", 1.2)),
            rework_minutes_per_error=float(payload.get("rework_minutes_per_error", 8.0)),
            manual_exception_minutes=float(payload.get("manual_exception_minutes", 16.0)),
            atlas_exception_seconds=float(payload.get("atlas_exception_seconds", 18.0)),
            high_priority_pct=float(payload.get("high_priority_pct", 18.0)),
            period_label=str(payload.get("period_label", "month")),
            atlas_time_source=str(
                payload.get("atlas_time_source", "synthetic_assumption")
            ),
        )

    def to_business_scenario(self) -> BusinessScenario:
        return BusinessScenario(
            scenario_id=self.scenario_id,
            title=self.title,
            volume_per_period=self.operations_per_period,
            staff_count=self.staff_count,
            work_hours_per_staff=self.work_hours_per_staff,
            hourly_cost_brl=self.hourly_cost_brl,
            manual_minutes_per_item=self.manual_minutes_per_operation,
            atlas_seconds_per_automated_item=self.atlas_seconds_per_automated_operation,
            automation_rate_pct=self.automation_rate_pct,
            human_review_minutes_per_automated_item=(
                self.human_review_minutes_per_automated_operation
            ),
            manual_error_rate_pct=self.manual_error_rate_pct,
            atlas_error_rate_pct=self.atlas_error_rate_pct,
            rework_minutes_per_error=self.rework_minutes_per_error,
            period_label=self.period_label,
            atlas_time_source=self.atlas_time_source,
        )


@dataclass(frozen=True, slots=True)
class RetailSimulationResult:
    scenario: RetailScenario
    business: BusinessSimulationResult
    high_priority_operations: float
    manual_avg_exception_response_minutes: float
    atlas_avg_exception_response_minutes: float
    exception_response_reduction_pct: float
    manual_operations_per_human_hour: float
    atlas_operations_per_human_hour: float


class RetailSimulationEngine:
    DISCLAIMER = (
        "Synthetic Retail Lab projection. Values estimate operational workload "
        "only; they do not guarantee savings, sales, stock accuracy, or staffing outcomes."
    )

    def simulate(self, scenario: RetailScenario) -> RetailSimulationResult:
        business = BusinessSimulationEngine().simulate(scenario.to_business_scenario())
        volume = float(scenario.operations_per_period)
        automation_rate = scenario.automation_rate_pct / 100.0
        high_priority_operations = volume * scenario.high_priority_pct / 100.0
        atlas_exception_minutes = scenario.atlas_exception_seconds / 60.0
        atlas_avg_exception_response_minutes = (
            automation_rate * atlas_exception_minutes
            + (1.0 - automation_rate) * scenario.manual_exception_minutes
        )
        return RetailSimulationResult(
            scenario=scenario,
            business=business,
            high_priority_operations=round(high_priority_operations, 3),
            manual_avg_exception_response_minutes=round(
                scenario.manual_exception_minutes, 3
            ),
            atlas_avg_exception_response_minutes=round(
                atlas_avg_exception_response_minutes, 3
            ),
            exception_response_reduction_pct=round(
                self._reduction_pct(
                    scenario.manual_exception_minutes,
                    atlas_avg_exception_response_minutes,
                ),
                3,
            ),
            manual_operations_per_human_hour=round(
                self._safe_rate(volume, business.manual_human_hours), 3
            ),
            atlas_operations_per_human_hour=round(
                self._safe_rate(volume, business.atlas_human_hours), 3
            ),
        )

    @staticmethod
    def generate_events(
        scenario: RetailScenario,
        *,
        seed: int,
        count: int | None = None,
    ) -> tuple[SyntheticRetailEvent, ...]:
        total = scenario.operations_per_period if count is None else int(count)
        if total < 0:
            raise ValueError("count cannot be negative")
        rng = random.Random(int(seed))
        priorities = ("normal", "high")
        templates = {
            "stock_check": "Verificar estoque do item sintetico {index}.",
            "price_divergence": "Validar divergencia de preco do item {index}.",
            "supplier_order": "Consultar status do pedido sintetico {index}.",
            "sales_report": "Consolidar relatorio sintetico {index}.",
        }
        events: list[SyntheticRetailEvent] = []
        high_probability = scenario.high_priority_pct / 100.0
        for index in range(total):
            category = rng.choice(scenario.categories)
            priority = priorities[1] if rng.random() < high_probability else priorities[0]
            template = templates.get(category, "Processar evento sintetico {index}.")
            events.append(
                SyntheticRetailEvent(
                    event_id=f"RT-SIM-{index + 1:06d}",
                    category=category,
                    priority=priority,
                    message=template.format(index=index + 1),
                )
            )
        return tuple(events)

    @staticmethod
    def _reduction_pct(baseline: float, assisted: float) -> float:
        if baseline <= 0:
            return 0.0
        return (baseline - assisted) / baseline * 100.0

    @staticmethod
    def _safe_rate(items: float, hours: float) -> float:
        return items / hours if hours > 0 else 0.0


@dataclass(frozen=True, slots=True)
class SyntheticOfficeTask:
    task_id: str
    category: str
    urgency: str
    message: str


@dataclass(frozen=True, slots=True)
class OfficeScenario:
    scenario_id: str
    title: str
    tasks_per_period: int
    staff_count: int
    work_hours_per_staff: float
    hourly_cost_brl: float
    categories: tuple[str, ...]
    automation_rate_pct: float
    manual_minutes_per_task: float
    atlas_seconds_per_automated_task: float
    human_review_minutes_per_automated_task: float
    manual_error_rate_pct: float
    atlas_error_rate_pct: float
    rework_minutes_per_error: float
    manual_first_action_minutes: float
    atlas_first_action_seconds: float
    manual_on_time_pct: float
    atlas_automated_on_time_pct: float
    period_label: str = "month"
    atlas_time_source: str = "synthetic_assumption"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.title.strip():
            raise ValueError("scenario_id and title cannot be empty")
        if self.tasks_per_period <= 0:
            raise ValueError("tasks_per_period must be positive")
        if self.staff_count <= 0 or self.work_hours_per_staff <= 0:
            raise ValueError("staff capacity must be positive")
        if self.hourly_cost_brl < 0:
            raise ValueError("hourly_cost_brl cannot be negative")
        if not self.categories:
            raise ValueError("categories cannot be empty")
        for name in (
            "automation_rate_pct",
            "manual_error_rate_pct",
            "atlas_error_rate_pct",
            "manual_on_time_pct",
            "atlas_automated_on_time_pct",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be between 0 and 100")
        for name in (
            "manual_minutes_per_task",
            "atlas_seconds_per_automated_task",
            "human_review_minutes_per_automated_task",
            "rework_minutes_per_error",
            "manual_first_action_minutes",
            "atlas_first_action_seconds",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "OfficeScenario":
        raw_categories = payload.get(
            "categories",
            ("email", "report", "spreadsheet", "scheduling", "file_organization"),
        )
        if not isinstance(raw_categories, (list, tuple)):
            raise ValueError("categories must be a list or tuple")
        return cls(
            scenario_id=str(payload.get("scenario_id", "office.synthetic")),
            title=str(payload.get("title", "Synthetic Office Operations")),
            tasks_per_period=int(payload.get("tasks_per_period", 1800)),
            staff_count=int(payload.get("staff_count", 5)),
            work_hours_per_staff=float(payload.get("work_hours_per_staff", 176.0)),
            hourly_cost_brl=float(payload.get("hourly_cost_brl", 26.0)),
            categories=tuple(str(item) for item in raw_categories),
            automation_rate_pct=float(payload.get("automation_rate_pct", 72.0)),
            manual_minutes_per_task=float(payload.get("manual_minutes_per_task", 7.5)),
            atlas_seconds_per_automated_task=float(
                payload.get("atlas_seconds_per_automated_task", 25.0)
            ),
            human_review_minutes_per_automated_task=float(
                payload.get("human_review_minutes_per_automated_task", 1.0)
            ),
            manual_error_rate_pct=float(payload.get("manual_error_rate_pct", 5.0)),
            atlas_error_rate_pct=float(payload.get("atlas_error_rate_pct", 1.0)),
            rework_minutes_per_error=float(payload.get("rework_minutes_per_error", 10.0)),
            manual_first_action_minutes=float(payload.get("manual_first_action_minutes", 55.0)),
            atlas_first_action_seconds=float(payload.get("atlas_first_action_seconds", 12.0)),
            manual_on_time_pct=float(payload.get("manual_on_time_pct", 86.0)),
            atlas_automated_on_time_pct=float(
                payload.get("atlas_automated_on_time_pct", 99.0)
            ),
            period_label=str(payload.get("period_label", "month")),
            atlas_time_source=str(
                payload.get("atlas_time_source", "synthetic_assumption")
            ),
        )

    def to_business_scenario(self) -> BusinessScenario:
        return BusinessScenario(
            scenario_id=self.scenario_id,
            title=self.title,
            volume_per_period=self.tasks_per_period,
            staff_count=self.staff_count,
            work_hours_per_staff=self.work_hours_per_staff,
            hourly_cost_brl=self.hourly_cost_brl,
            manual_minutes_per_item=self.manual_minutes_per_task,
            atlas_seconds_per_automated_item=self.atlas_seconds_per_automated_task,
            automation_rate_pct=self.automation_rate_pct,
            human_review_minutes_per_automated_item=(
                self.human_review_minutes_per_automated_task
            ),
            manual_error_rate_pct=self.manual_error_rate_pct,
            atlas_error_rate_pct=self.atlas_error_rate_pct,
            rework_minutes_per_error=self.rework_minutes_per_error,
            period_label=self.period_label,
            atlas_time_source=self.atlas_time_source,
        )


@dataclass(frozen=True, slots=True)
class OfficeSimulationResult:
    scenario: OfficeScenario
    business: BusinessSimulationResult
    manual_avg_first_action_minutes: float
    atlas_avg_first_action_minutes: float
    first_action_reduction_pct: float
    manual_on_time_tasks: float
    atlas_on_time_tasks: float
    manual_on_time_pct: float
    atlas_on_time_pct: float
    manual_tasks_per_human_hour: float
    atlas_tasks_per_human_hour: float


class OfficeSimulationEngine:
    DISCLAIMER = (
        "Synthetic Office Lab projection. Values estimate administrative workload "
        "only; they do not guarantee savings, deadlines, quality, or staffing outcomes."
    )

    def simulate(self, scenario: OfficeScenario) -> OfficeSimulationResult:
        business = BusinessSimulationEngine().simulate(scenario.to_business_scenario())
        volume = float(scenario.tasks_per_period)
        automation_rate = scenario.automation_rate_pct / 100.0
        atlas_first_action_minutes = scenario.atlas_first_action_seconds / 60.0
        atlas_avg_first_action_minutes = (
            automation_rate * atlas_first_action_minutes
            + (1.0 - automation_rate) * scenario.manual_first_action_minutes
        )
        manual_on_time_tasks = volume * scenario.manual_on_time_pct / 100.0
        atlas_on_time_tasks = (
            volume
            * automation_rate
            * scenario.atlas_automated_on_time_pct
            / 100.0
            + volume
            * (1.0 - automation_rate)
            * scenario.manual_on_time_pct
            / 100.0
        )
        atlas_on_time_pct = atlas_on_time_tasks / volume * 100.0 if volume else 0.0
        return OfficeSimulationResult(
            scenario=scenario,
            business=business,
            manual_avg_first_action_minutes=round(
                scenario.manual_first_action_minutes, 3
            ),
            atlas_avg_first_action_minutes=round(atlas_avg_first_action_minutes, 3),
            first_action_reduction_pct=round(
                self._reduction_pct(
                    scenario.manual_first_action_minutes,
                    atlas_avg_first_action_minutes,
                ),
                3,
            ),
            manual_on_time_tasks=round(manual_on_time_tasks, 3),
            atlas_on_time_tasks=round(atlas_on_time_tasks, 3),
            manual_on_time_pct=round(scenario.manual_on_time_pct, 3),
            atlas_on_time_pct=round(atlas_on_time_pct, 3),
            manual_tasks_per_human_hour=round(
                self._safe_rate(volume, business.manual_human_hours), 3
            ),
            atlas_tasks_per_human_hour=round(
                self._safe_rate(volume, business.atlas_human_hours), 3
            ),
        )

    @staticmethod
    def generate_tasks(
        scenario: OfficeScenario,
        *,
        seed: int,
        count: int | None = None,
    ) -> tuple[SyntheticOfficeTask, ...]:
        total = scenario.tasks_per_period if count is None else int(count)
        if total < 0:
            raise ValueError("count cannot be negative")
        rng = random.Random(int(seed))
        urgencies = ("normal", "priority")
        templates = {
            "email": "Preparar email sintetico {index}.",
            "report": "Consolidar relatorio sintetico {index}.",
            "spreadsheet": "Atualizar planilha sintetica {index}.",
            "scheduling": "Organizar agenda sintetica {index}.",
            "file_organization": "Organizar arquivo sintetico {index}.",
        }
        tasks: list[SyntheticOfficeTask] = []
        for index in range(total):
            category = rng.choice(scenario.categories)
            urgency = rng.choice(urgencies)
            template = templates.get(category, "Processar tarefa sintetica {index}.")
            tasks.append(
                SyntheticOfficeTask(
                    task_id=f"OF-SIM-{index + 1:06d}",
                    category=category,
                    urgency=urgency,
                    message=template.format(index=index + 1),
                )
            )
        return tuple(tasks)

    @staticmethod
    def _reduction_pct(baseline: float, assisted: float) -> float:
        if baseline <= 0:
            return 0.0
        return (baseline - assisted) / baseline * 100.0

    @staticmethod
    def _safe_rate(items: float, hours: float) -> float:
        return items / hours if hours > 0 else 0.0


def retail_dashboard_payload(result: RetailSimulationResult) -> dict[str, object]:
    scenario = result.scenario
    business = result.business
    return {
        "schema_version": "1.0",
        "kind": "retail_simulation",
        "scenario": {
            "id": scenario.scenario_id,
            "title": scenario.title,
            "period": scenario.period_label,
            "operations": scenario.operations_per_period,
            "staff_count": scenario.staff_count,
            "atlas_time_source": scenario.atlas_time_source,
        },
        "exceptions": {
            "high_priority_operations": result.high_priority_operations,
            "manual_avg_response_minutes": result.manual_avg_exception_response_minutes,
            "atlas_avg_response_minutes": result.atlas_avg_exception_response_minutes,
            "response_reduction_pct": result.exception_response_reduction_pct,
        },
        "workload": {
            "manual_human_hours": business.manual_human_hours,
            "atlas_human_hours": business.atlas_human_hours,
            "human_hours_liberated": business.human_hours_liberated,
            "human_time_reduction_pct": business.human_time_reduction_pct,
            "manual_operations_per_human_hour": result.manual_operations_per_human_hour,
            "atlas_operations_per_human_hour": result.atlas_operations_per_human_hour,
        },
        "quality": {
            "manual_expected_errors": business.manual_expected_errors,
            "atlas_expected_errors": business.atlas_expected_errors,
        },
        "economics": {
            "potential_capacity_value_brl": business.potential_capacity_value_brl,
            "annual_potential_capacity_value_brl": (
                business.annual_potential_capacity_value_brl
            ),
        },
        "frontend": {"lab": "retail", "ready": True},
        "disclaimer": RetailSimulationEngine.DISCLAIMER,
    }


def office_dashboard_payload(result: OfficeSimulationResult) -> dict[str, object]:
    scenario = result.scenario
    business = result.business
    return {
        "schema_version": "1.0",
        "kind": "office_simulation",
        "scenario": {
            "id": scenario.scenario_id,
            "title": scenario.title,
            "period": scenario.period_label,
            "tasks": scenario.tasks_per_period,
            "staff_count": scenario.staff_count,
            "atlas_time_source": scenario.atlas_time_source,
        },
        "turnaround": {
            "manual_avg_first_action_minutes": result.manual_avg_first_action_minutes,
            "atlas_avg_first_action_minutes": result.atlas_avg_first_action_minutes,
            "first_action_reduction_pct": result.first_action_reduction_pct,
        },
        "deadlines": {
            "manual_on_time_tasks": result.manual_on_time_tasks,
            "atlas_on_time_tasks": result.atlas_on_time_tasks,
            "manual_on_time_pct": result.manual_on_time_pct,
            "atlas_on_time_pct": result.atlas_on_time_pct,
        },
        "workload": {
            "manual_human_hours": business.manual_human_hours,
            "atlas_human_hours": business.atlas_human_hours,
            "human_hours_liberated": business.human_hours_liberated,
            "human_time_reduction_pct": business.human_time_reduction_pct,
            "manual_tasks_per_human_hour": result.manual_tasks_per_human_hour,
            "atlas_tasks_per_human_hour": result.atlas_tasks_per_human_hour,
        },
        "economics": {
            "potential_capacity_value_brl": business.potential_capacity_value_brl,
            "annual_potential_capacity_value_brl": (
                business.annual_potential_capacity_value_brl
            ),
        },
        "frontend": {"lab": "office", "ready": True},
        "disclaimer": OfficeSimulationEngine.DISCLAIMER,
    }
