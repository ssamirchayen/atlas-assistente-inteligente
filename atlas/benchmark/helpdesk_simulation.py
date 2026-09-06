"""Synthetic Help Desk + Provisioning simulator for Sprint 27 stage 9.

The lab compares explicit manual assumptions with an Atlas-assisted operating
model. It is intentionally deterministic and does not claim measured customer
savings, service-level guarantees, staffing reductions, or incident outcomes.
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
class SyntheticHelpDeskTicket:
    """Privacy-safe deterministic service ticket used by the Help Desk Lab."""

    ticket_id: str
    category: str
    severity: str
    remote_eligible: bool
    message: str


@dataclass(frozen=True, slots=True)
class HelpDeskScenario:
    """Explicit assumptions for support tickets and PC provisioning."""

    scenario_id: str
    title: str
    tickets_per_period: int
    technician_count: int
    work_hours_per_technician: float
    hourly_cost_brl: float
    managed_devices: int
    onboardings_per_period: int
    ticket_categories: tuple[str, ...]
    automation_rate_pct: float
    manual_triage_minutes: float
    manual_resolution_minutes: float
    atlas_processing_seconds_per_automated_ticket: float
    human_review_minutes_per_automated_ticket: float
    manual_first_response_minutes: float
    atlas_first_response_seconds: float
    manual_error_rate_pct: float
    atlas_error_rate_pct: float
    rework_minutes_per_error: float
    manual_escalation_rate_pct: float
    atlas_escalation_rate_pct: float
    manual_provisioning_minutes: float
    atlas_provisioning_minutes: float
    provisioning_automation_rate_pct: float
    human_review_minutes_per_automated_provisioning: float
    period_label: str = "month"
    atlas_time_source: str = "synthetic_assumption"

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if self.tickets_per_period <= 0:
            raise ValueError("tickets_per_period must be positive")
        if self.technician_count <= 0:
            raise ValueError("technician_count must be positive")
        if self.work_hours_per_technician <= 0:
            raise ValueError("work_hours_per_technician must be positive")
        if self.hourly_cost_brl < 0:
            raise ValueError("hourly_cost_brl cannot be negative")
        if self.managed_devices <= 0:
            raise ValueError("managed_devices must be positive")
        if self.onboardings_per_period < 0:
            raise ValueError("onboardings_per_period cannot be negative")
        if not self.ticket_categories:
            raise ValueError("ticket_categories cannot be empty")
        for name in (
            "automation_rate_pct",
            "manual_error_rate_pct",
            "atlas_error_rate_pct",
            "manual_escalation_rate_pct",
            "atlas_escalation_rate_pct",
            "provisioning_automation_rate_pct",
        ):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be between 0 and 100")
        for name in (
            "manual_triage_minutes",
            "manual_resolution_minutes",
            "atlas_processing_seconds_per_automated_ticket",
            "human_review_minutes_per_automated_ticket",
            "manual_first_response_minutes",
            "atlas_first_response_seconds",
            "rework_minutes_per_error",
            "manual_provisioning_minutes",
            "atlas_provisioning_minutes",
            "human_review_minutes_per_automated_provisioning",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.manual_triage_minutes + self.manual_resolution_minutes <= 0:
            raise ValueError("manual ticket workload must be positive")
        if not self.period_label.strip():
            raise ValueError("period_label cannot be empty")
        if not self.atlas_time_source.strip():
            raise ValueError("atlas_time_source cannot be empty")

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "HelpDeskScenario":
        categories = payload.get(
            "ticket_categories",
            [
                "password_access",
                "printing",
                "network",
                "slow_pc",
                "software_install",
                "email",
                "shared_folder",
            ],
        )
        if not isinstance(categories, (list, tuple)):
            raise ValueError("ticket_categories must be a list")
        return cls(
            scenario_id=str(payload.get("scenario_id", "helpdesk.synthetic")),
            title=str(payload.get("title", "Synthetic Help Desk + Provisioning")),
            tickets_per_period=int(payload.get("tickets_per_period", 1200)),
            technician_count=int(payload.get("technician_count", 4)),
            work_hours_per_technician=float(
                payload.get("work_hours_per_technician", 176.0)
            ),
            hourly_cost_brl=float(payload.get("hourly_cost_brl", 28.0)),
            managed_devices=int(payload.get("managed_devices", 100)),
            onboardings_per_period=int(payload.get("onboardings_per_period", 15)),
            ticket_categories=tuple(str(item) for item in categories),
            automation_rate_pct=float(payload.get("automation_rate_pct", 70.0)),
            manual_triage_minutes=float(payload.get("manual_triage_minutes", 5.0)),
            manual_resolution_minutes=float(
                payload.get("manual_resolution_minutes", 22.0)
            ),
            atlas_processing_seconds_per_automated_ticket=float(
                payload.get("atlas_processing_seconds_per_automated_ticket", 45.0)
            ),
            human_review_minutes_per_automated_ticket=float(
                payload.get("human_review_minutes_per_automated_ticket", 2.0)
            ),
            manual_first_response_minutes=float(
                payload.get("manual_first_response_minutes", 18.0)
            ),
            atlas_first_response_seconds=float(
                payload.get("atlas_first_response_seconds", 10.0)
            ),
            manual_error_rate_pct=float(
                payload.get("manual_error_rate_pct", 6.0)
            ),
            atlas_error_rate_pct=float(payload.get("atlas_error_rate_pct", 1.5)),
            rework_minutes_per_error=float(
                payload.get("rework_minutes_per_error", 12.0)
            ),
            manual_escalation_rate_pct=float(
                payload.get("manual_escalation_rate_pct", 30.0)
            ),
            atlas_escalation_rate_pct=float(
                payload.get("atlas_escalation_rate_pct", 12.0)
            ),
            manual_provisioning_minutes=float(
                payload.get("manual_provisioning_minutes", 45.0)
            ),
            atlas_provisioning_minutes=float(
                payload.get("atlas_provisioning_minutes", 8.0)
            ),
            provisioning_automation_rate_pct=float(
                payload.get("provisioning_automation_rate_pct", 80.0)
            ),
            human_review_minutes_per_automated_provisioning=float(
                payload.get(
                    "human_review_minutes_per_automated_provisioning",
                    3.0,
                )
            ),
            period_label=str(payload.get("period_label", "month")),
            atlas_time_source=str(
                payload.get("atlas_time_source", "synthetic_assumption")
            ),
        )

    @property
    def manual_minutes_per_ticket(self) -> float:
        return self.manual_triage_minutes + self.manual_resolution_minutes

    def to_business_scenario(self) -> BusinessScenario:
        return BusinessScenario(
            scenario_id=self.scenario_id,
            title=self.title,
            volume_per_period=self.tickets_per_period,
            staff_count=self.technician_count,
            work_hours_per_staff=self.work_hours_per_technician,
            hourly_cost_brl=self.hourly_cost_brl,
            manual_minutes_per_item=self.manual_minutes_per_ticket,
            atlas_seconds_per_automated_item=(
                self.atlas_processing_seconds_per_automated_ticket
            ),
            automation_rate_pct=self.automation_rate_pct,
            human_review_minutes_per_automated_item=(
                self.human_review_minutes_per_automated_ticket
            ),
            manual_error_rate_pct=self.manual_error_rate_pct,
            atlas_error_rate_pct=self.atlas_error_rate_pct,
            rework_minutes_per_error=self.rework_minutes_per_error,
            period_label=self.period_label,
            atlas_time_source=self.atlas_time_source,
        )


@dataclass(frozen=True, slots=True)
class HelpDeskSimulationResult:
    """Help Desk metrics plus combined ticket/provisioning workload."""

    scenario: HelpDeskScenario
    ticket_business: BusinessSimulationResult
    manual_avg_first_response_minutes: float
    atlas_avg_first_response_minutes: float
    first_response_reduction_pct: float
    manual_expected_escalations: float
    atlas_expected_escalations: float
    manual_provisioning_human_hours: float
    atlas_provisioning_human_hours: float
    atlas_provisioning_machine_hours: float
    manual_avg_provisioning_elapsed_minutes: float
    atlas_avg_provisioning_elapsed_minutes: float
    provisioning_elapsed_reduction_pct: float
    total_manual_human_hours: float
    total_atlas_human_hours: float
    total_atlas_machine_hours: float
    human_hours_liberated: float
    human_time_reduction_pct: float
    manual_utilization_pct: float
    atlas_human_utilization_pct: float
    manual_operations_per_human_hour: float
    atlas_operations_per_human_hour: float
    potential_capacity_value_brl: float
    annual_potential_capacity_value_brl: float


class HelpDeskSimulationEngine:
    """Deterministic expected-value simulator for support operations."""

    DISCLAIMER = (
        "Synthetic Help Desk Lab projection. It estimates operational workload "
        "and capacity only; it does not guarantee SLA, incident resolution, "
        "staff reduction, savings, or real customer outcomes."
    )

    def simulate(self, scenario: HelpDeskScenario) -> HelpDeskSimulationResult:
        ticket_business = BusinessSimulationEngine().simulate(
            scenario.to_business_scenario()
        )
        ticket_automation = scenario.automation_rate_pct / 100.0
        provisioning_automation = scenario.provisioning_automation_rate_pct / 100.0

        atlas_auto_response_minutes = scenario.atlas_first_response_seconds / 60.0
        atlas_avg_first_response_minutes = (
            ticket_automation * atlas_auto_response_minutes
            + (1.0 - ticket_automation) * scenario.manual_first_response_minutes
        )
        first_response_reduction_pct = self._reduction_pct(
            scenario.manual_first_response_minutes,
            atlas_avg_first_response_minutes,
        )

        ticket_volume = float(scenario.tickets_per_period)
        manual_expected_escalations = (
            ticket_volume * scenario.manual_escalation_rate_pct / 100.0
        )
        atlas_expected_escalations = (
            ticket_volume
            * ticket_automation
            * scenario.atlas_escalation_rate_pct
            / 100.0
            + ticket_volume
            * (1.0 - ticket_automation)
            * scenario.manual_escalation_rate_pct
            / 100.0
        )

        onboardings = float(scenario.onboardings_per_period)
        automated_onboardings = onboardings * provisioning_automation
        manual_onboardings_remaining = onboardings - automated_onboardings
        manual_provisioning_human_hours = (
            onboardings * scenario.manual_provisioning_minutes / 60.0
        )
        atlas_provisioning_human_hours = (
            manual_onboardings_remaining * scenario.manual_provisioning_minutes / 60.0
            + automated_onboardings
            * scenario.human_review_minutes_per_automated_provisioning
            / 60.0
        )
        atlas_provisioning_machine_hours = (
            automated_onboardings * scenario.atlas_provisioning_minutes / 60.0
        )
        atlas_avg_provisioning_elapsed_minutes = (
            provisioning_automation * scenario.atlas_provisioning_minutes
            + (1.0 - provisioning_automation) * scenario.manual_provisioning_minutes
        )
        provisioning_elapsed_reduction_pct = self._reduction_pct(
            scenario.manual_provisioning_minutes,
            atlas_avg_provisioning_elapsed_minutes,
        )

        total_manual_human_hours = (
            ticket_business.manual_human_hours + manual_provisioning_human_hours
        )
        total_atlas_human_hours = (
            ticket_business.atlas_human_hours + atlas_provisioning_human_hours
        )
        total_atlas_machine_hours = (
            ticket_business.atlas_machine_hours + atlas_provisioning_machine_hours
        )
        human_hours_liberated = total_manual_human_hours - total_atlas_human_hours
        human_time_reduction_pct = self._reduction_pct(
            total_manual_human_hours,
            total_atlas_human_hours,
        )
        available_human_hours = (
            scenario.technician_count * scenario.work_hours_per_technician
        )
        manual_utilization_pct = self._ratio_pct(
            total_manual_human_hours,
            available_human_hours,
        )
        atlas_human_utilization_pct = self._ratio_pct(
            total_atlas_human_hours,
            available_human_hours,
        )
        total_operations = ticket_volume + onboardings
        manual_operations_per_human_hour = self._safe_rate(
            total_operations,
            total_manual_human_hours,
        )
        atlas_operations_per_human_hour = self._safe_rate(
            total_operations,
            total_atlas_human_hours,
        )
        potential_capacity_value_brl = (
            human_hours_liberated * scenario.hourly_cost_brl
        )

        return HelpDeskSimulationResult(
            scenario=scenario,
            ticket_business=ticket_business,
            manual_avg_first_response_minutes=round(
                scenario.manual_first_response_minutes,
                3,
            ),
            atlas_avg_first_response_minutes=round(
                atlas_avg_first_response_minutes,
                3,
            ),
            first_response_reduction_pct=round(first_response_reduction_pct, 3),
            manual_expected_escalations=round(manual_expected_escalations, 3),
            atlas_expected_escalations=round(atlas_expected_escalations, 3),
            manual_provisioning_human_hours=round(
                manual_provisioning_human_hours,
                3,
            ),
            atlas_provisioning_human_hours=round(
                atlas_provisioning_human_hours,
                3,
            ),
            atlas_provisioning_machine_hours=round(
                atlas_provisioning_machine_hours,
                3,
            ),
            manual_avg_provisioning_elapsed_minutes=round(
                scenario.manual_provisioning_minutes,
                3,
            ),
            atlas_avg_provisioning_elapsed_minutes=round(
                atlas_avg_provisioning_elapsed_minutes,
                3,
            ),
            provisioning_elapsed_reduction_pct=round(
                provisioning_elapsed_reduction_pct,
                3,
            ),
            total_manual_human_hours=round(total_manual_human_hours, 3),
            total_atlas_human_hours=round(total_atlas_human_hours, 3),
            total_atlas_machine_hours=round(total_atlas_machine_hours, 3),
            human_hours_liberated=round(human_hours_liberated, 3),
            human_time_reduction_pct=round(human_time_reduction_pct, 3),
            manual_utilization_pct=round(manual_utilization_pct, 3),
            atlas_human_utilization_pct=round(atlas_human_utilization_pct, 3),
            manual_operations_per_human_hour=round(
                manual_operations_per_human_hour,
                3,
            ),
            atlas_operations_per_human_hour=round(
                atlas_operations_per_human_hour,
                3,
            ),
            potential_capacity_value_brl=round(potential_capacity_value_brl, 2),
            annual_potential_capacity_value_brl=round(
                potential_capacity_value_brl * 12.0,
                2,
            ),
        )

    @staticmethod
    def generate_tickets(
        scenario: HelpDeskScenario,
        *,
        seed: int,
        count: int | None = None,
    ) -> tuple[SyntheticHelpDeskTicket, ...]:
        """Generate deterministic synthetic support tickets without personal data."""

        total = scenario.tickets_per_period if count is None else int(count)
        if total < 0:
            raise ValueError("count cannot be negative")
        rng = random.Random(int(seed))
        severities = ("low", "medium", "high")
        remote_categories = {
            "password_access",
            "printing",
            "slow_pc",
            "software_install",
            "email",
            "shared_folder",
        }
        templates = {
            "password_access": "Usuario simulado nao consegue acessar a conta.",
            "printing": "Impressora do laboratorio simulado nao responde.",
            "network": "Estacao simulada perdeu conectividade de rede.",
            "slow_pc": "Computador simulado apresenta lentidao.",
            "software_install": "Instalar aplicativo homologado na estacao simulada.",
            "email": "Cliente de email simulado nao sincroniza.",
            "shared_folder": "Pasta compartilhada simulada nao esta acessivel.",
        }
        tickets: list[SyntheticHelpDeskTicket] = []
        for index in range(total):
            category = rng.choice(scenario.ticket_categories)
            tickets.append(
                SyntheticHelpDeskTicket(
                    ticket_id=f"HD-SIM-{index + 1:06d}",
                    category=category,
                    severity=rng.choice(severities),
                    remote_eligible=category in remote_categories,
                    message=templates.get(
                        category,
                        f"Chamado sintetico da categoria {category}.",
                    ),
                )
            )
        return tuple(tickets)

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


def helpdesk_dashboard_payload(
    result: HelpDeskSimulationResult,
) -> dict[str, object]:
    """Stable JSON-safe payload reserved for the mini benchmark frontend."""

    scenario = result.scenario
    ticket_business = result.ticket_business
    return {
        "schema_version": "1.0",
        "kind": "helpdesk_provisioning_simulation",
        "scenario": {
            "id": scenario.scenario_id,
            "title": scenario.title,
            "period": scenario.period_label,
            "tickets": scenario.tickets_per_period,
            "technicians": scenario.technician_count,
            "managed_devices": scenario.managed_devices,
            "onboardings": scenario.onboardings_per_period,
            "categories": list(scenario.ticket_categories),
            "atlas_time_source": scenario.atlas_time_source,
        },
        "response": {
            "manual_avg_first_response_minutes": (
                result.manual_avg_first_response_minutes
            ),
            "atlas_avg_first_response_minutes": result.atlas_avg_first_response_minutes,
            "first_response_reduction_pct": result.first_response_reduction_pct,
        },
        "automation": {
            "ticket_automation_rate_pct": scenario.automation_rate_pct,
            "manual_expected_escalations": result.manual_expected_escalations,
            "atlas_expected_escalations": result.atlas_expected_escalations,
        },
        "provisioning": {
            "automation_rate_pct": scenario.provisioning_automation_rate_pct,
            "manual_human_hours": result.manual_provisioning_human_hours,
            "atlas_human_hours": result.atlas_provisioning_human_hours,
            "atlas_machine_hours": result.atlas_provisioning_machine_hours,
            "manual_avg_elapsed_minutes": (
                result.manual_avg_provisioning_elapsed_minutes
            ),
            "atlas_avg_elapsed_minutes": result.atlas_avg_provisioning_elapsed_minutes,
            "elapsed_reduction_pct": result.provisioning_elapsed_reduction_pct,
        },
        "workload": {
            "manual_human_hours": result.total_manual_human_hours,
            "atlas_human_hours": result.total_atlas_human_hours,
            "atlas_machine_hours": result.total_atlas_machine_hours,
            "human_hours_liberated": result.human_hours_liberated,
            "human_time_reduction_pct": result.human_time_reduction_pct,
            "manual_utilization_pct": result.manual_utilization_pct,
            "atlas_human_utilization_pct": result.atlas_human_utilization_pct,
            "manual_operations_per_human_hour": (
                result.manual_operations_per_human_hour
            ),
            "atlas_operations_per_human_hour": result.atlas_operations_per_human_hour,
        },
        "quality": {
            "manual_expected_errors": ticket_business.manual_expected_errors,
            "atlas_expected_errors": ticket_business.atlas_expected_errors,
            "manual_escalation_rate_pct": scenario.manual_escalation_rate_pct,
            "atlas_escalation_rate_pct": scenario.atlas_escalation_rate_pct,
            "sla_guaranteed": False,
        },
        "economics": {
            "potential_capacity_value_brl": result.potential_capacity_value_brl,
            "annual_potential_capacity_value_brl": (
                result.annual_potential_capacity_value_brl
            ),
        },
        "frontend": {
            "recommended_cards": [
                "tickets",
                "first_response",
                "human_hours_liberated",
                "provisioning_time",
                "operations_per_human_hour",
            ],
            "recommended_comparison": "manual_vs_atlas",
        },
        "disclaimer": HelpDeskSimulationEngine.DISCLAIMER,
    }
