"""Snapshot administrativo somente leitura e sem dados sensíveis."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from atlas.core.lazy import LazyState
from atlas.core.resource_manager import ResourcePressure
from atlas.core.runtime_profile import RuntimeSupportStatus


class AdminHealth(StrEnum):
    HEALTHY = "healthy"
    ATTENTION = "attention"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


class AdminKernel(Protocol):
    runtime_profile: Any
    resource_manager: Any
    lazy_components: Any
    _brain_component: Any


@dataclass(frozen=True, slots=True)
class AdminSnapshot:
    generated_at: datetime
    health: AdminHealth
    profile: Mapping[str, object]
    resources: Mapping[str, object]
    lazy_components: tuple[Mapping[str, object], ...]
    model_route: Mapping[str, object] | None
    resource_audit: Mapping[str, object]
    capabilities: Mapping[str, bool]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.generated_at, datetime) or self.generated_at.tzinfo is None:
            raise ValueError("generated_at deve possuir fuso horário.")
        object.__setattr__(
            self,
            "generated_at",
            self.generated_at.astimezone(timezone.utc),
        )
        if not isinstance(self.health, AdminHealth):
            raise TypeError("health deve ser AdminHealth.")
        if not self.reason_codes or len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes deve ser único e não vazio.")

    def public_summary(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "health": self.health.value,
            "profile": dict(self.profile),
            "resources": dict(self.resources),
            "lazy_components": [dict(item) for item in self.lazy_components],
            "model_route": (
                None if self.model_route is None else dict(self.model_route)
            ),
            "resource_audit": dict(self.resource_audit),
            "capabilities": dict(self.capabilities),
            "reason_codes": self.reason_codes,
        }


class AdminConsoleService:
    """Agrega diagnósticos existentes sem executar ou alterar o Atlas."""

    def __init__(
        self,
        kernel: AdminKernel,
        *,
        clock=None,
    ) -> None:
        self._kernel = kernel
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(self) -> AdminSnapshot:
        reasons: list[str] = []
        profile = self._profile_summary(reasons)
        resources = self._resource_summary(reasons)
        lazy = self._lazy_summary(reasons)
        model_route = self._model_summary(reasons)
        audit = self._audit_summary(reasons)
        health = self._health(profile, resources, reasons)
        return AdminSnapshot(
            generated_at=self._clock(),
            health=health,
            profile=self._freeze(profile),
            resources=self._freeze(resources),
            lazy_components=tuple(self._freeze(item) for item in lazy),
            model_route=(
                None if model_route is None else self._freeze(model_route)
            ),
            resource_audit=self._freeze(audit),
            capabilities=self._freeze(
                {
                    "read_only": True,
                    "local_console": True,
                    "mutating_controls": False,
                    "loads_lazy_components": False,
                }
            ),
            reason_codes=tuple(dict.fromkeys(reasons or ["systems_healthy"])),
        )

    def _profile_summary(self, reasons: list[str]) -> dict[str, object]:
        try:
            summary = dict(self._kernel.runtime_profile.public_summary())
            summary["available"] = True
            return summary
        except (AttributeError, RuntimeError, TypeError, ValueError):
            reasons.append("profile_unavailable")
            return {"available": False, "reason_code": "profile_unavailable"}

    def _resource_summary(self, reasons: list[str]) -> dict[str, object]:
        try:
            summary = dict(self._kernel.resource_manager.status().public_summary())
            summary["available"] = True
            return summary
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            reasons.append("resource_metrics_unavailable")
            return {
                "available": False,
                "reason_code": "resource_metrics_unavailable",
            }

    def _lazy_summary(self, reasons: list[str]) -> list[dict[str, object]]:
        try:
            snapshots = self._kernel.lazy_components.snapshots()
            if any(item.state is LazyState.FAILED for item in snapshots):
                reasons.append("lazy_component_failed")
            return [
                {
                    "name": item.name,
                    "state": item.state.value,
                    "loaded": item.loaded,
                    "load_attempts": item.load_attempts,
                    "successful_loads": item.successful_loads,
                    "load_duration_ms": (
                        None
                        if item.load_duration_ms is None
                        else round(item.load_duration_ms, 2)
                    ),
                    "last_error_type": item.last_error_type,
                }
                for item in snapshots
            ]
        except (AttributeError, RuntimeError, TypeError, ValueError):
            reasons.append("lazy_status_unavailable")
            return []

    def _model_summary(
        self,
        reasons: list[str],
    ) -> dict[str, object] | None:
        try:
            brain = self._kernel._brain_component.peek()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            reasons.append("model_status_unavailable")
            return None
        if brain is None:
            return None
        decision = getattr(brain, "last_model_decision", None)
        if decision is None:
            return None
        try:
            return dict(decision.public_summary())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            reasons.append("model_status_unavailable")
            return None

    def _audit_summary(self, reasons: list[str]) -> dict[str, object]:
        try:
            events = self._kernel.resource_manager.audit_events()
            actions = Counter(event.action.value for event in events)
            return {
                "available": True,
                "total_events": len(events),
                "admitted": actions.get("admitted", 0),
                "rejected": actions.get("rejected", 0),
                "released": actions.get("released", 0),
            }
        except (AttributeError, RuntimeError, TypeError, ValueError):
            reasons.append("resource_audit_unavailable")
            return {
                "available": False,
                "reason_code": "resource_audit_unavailable",
            }

    @staticmethod
    def _health(
        profile: Mapping[str, object],
        resources: Mapping[str, object],
        reasons: list[str],
    ) -> AdminHealth:
        if not profile.get("available") and not resources.get("available"):
            return AdminHealth.UNAVAILABLE
        pressure = resources.get("pressure")
        support = profile.get("support_status")
        if pressure == ResourcePressure.CRITICAL.value:
            reasons.append("resource_pressure_critical")
            return AdminHealth.CRITICAL
        if support == RuntimeSupportStatus.UNSUPPORTED.value:
            reasons.append("runtime_unsupported")
            return AdminHealth.CRITICAL
        if (
            pressure == ResourcePressure.WARNING.value
            or support == RuntimeSupportStatus.LIMITED.value
            or reasons
        ):
            reasons.append("attention_required")
            return AdminHealth.ATTENTION
        return AdminHealth.HEALTHY

    @staticmethod
    def _freeze(values: Mapping[str, Any]) -> Mapping[str, Any]:
        return MappingProxyType(dict(values))


__all__ = ["AdminConsoleService", "AdminHealth", "AdminSnapshot"]
