"""Resource Manager local, limitado e sem controle destrutivo do sistema."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from threading import RLock
from typing import Any
import re
from uuid import uuid4

import psutil

from atlas.core.runtime_profile import (
    GIB,
    RuntimeProfile,
    RuntimeProfileDecision,
    RuntimeSupportStatus,
)


MIB = 1024**2
_LEASE_ID = re.compile(r"^[a-f0-9]{32}$")


class ResourcePressure(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class WorkloadClass(StrEnum):
    LIGHT = "light"
    STANDARD = "standard"
    HEAVY = "heavy"


class AdmissionOutcome(StrEnum):
    ADMITTED = "admitted"
    REJECTED_CAPACITY = "rejected_capacity"
    REJECTED_METRICS = "rejected_metrics"
    REJECTED_PRESSURE = "rejected_pressure"
    REJECTED_UNSUPPORTED = "rejected_unsupported"


class ResourceAuditAction(StrEnum):
    ADMITTED = "admitted"
    REJECTED = "rejected"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class RuntimeMetrics:
    captured_at: datetime
    cpu_percent: float | None
    memory_percent: float
    available_memory_gb: float
    process_rss_mb: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.captured_at, datetime) or self.captured_at.tzinfo is None:
            raise ValueError("captured_at deve possuir fuso horário.")
        object.__setattr__(
            self,
            "captured_at",
            self.captured_at.astimezone(timezone.utc),
        )
        self._percentage("memory_percent", self.memory_percent)
        if self.cpu_percent is not None:
            self._percentage("cpu_percent", self.cpu_percent)
        self._non_negative("available_memory_gb", self.available_memory_gb)
        if self.process_rss_mb is not None:
            self._non_negative("process_rss_mb", self.process_rss_mb)

    @staticmethod
    def _percentage(label: str, value: float) -> None:
        RuntimeMetrics._non_negative(label, value)
        if value > 100:
            raise ValueError(f"{label} não pode superar 100.")

    @staticmethod
    def _non_negative(label: str, value: float) -> None:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
            or value < 0
        ):
            raise ValueError(f"{label} deve ser número finito não negativo.")


@dataclass(frozen=True, slots=True)
class ResourceThresholds:
    warning_cpu_percent: float = 90.0
    critical_cpu_percent: float = 98.0
    warning_memory_percent: float = 85.0
    critical_memory_percent: float = 95.0
    warning_available_memory_gb: float = 1.5
    critical_available_memory_gb: float = 0.5

    def __post_init__(self) -> None:
        for label in (
            "warning_cpu_percent",
            "critical_cpu_percent",
            "warning_memory_percent",
            "critical_memory_percent",
        ):
            RuntimeMetrics._percentage(label, getattr(self, label))
        for label in (
            "warning_available_memory_gb",
            "critical_available_memory_gb",
        ):
            RuntimeMetrics._non_negative(label, getattr(self, label))
        if self.warning_cpu_percent >= self.critical_cpu_percent:
            raise ValueError("O limite crítico de CPU deve superar o de alerta.")
        if self.warning_memory_percent >= self.critical_memory_percent:
            raise ValueError("O limite crítico de RAM deve superar o de alerta.")
        if (
            self.warning_available_memory_gb
            <= self.critical_available_memory_gb
        ):
            raise ValueError("O limite de RAM disponível em alerta deve ser maior.")


@dataclass(frozen=True, slots=True)
class PressureAssessment:
    pressure: ResourcePressure
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.reason_codes or len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes deve ser único e não vazio.")


@dataclass(frozen=True, slots=True)
class ResourceLease:
    lease_id: str
    workload: WorkloadClass
    acquired_at: datetime

    def __post_init__(self) -> None:
        if not _LEASE_ID.fullmatch(self.lease_id):
            raise ValueError("lease_id é inválido.")
        if not isinstance(self.workload, WorkloadClass):
            raise TypeError("workload deve ser WorkloadClass.")
        if not isinstance(self.acquired_at, datetime) or self.acquired_at.tzinfo is None:
            raise ValueError("acquired_at deve possuir fuso horário.")
        object.__setattr__(
            self,
            "acquired_at",
            self.acquired_at.astimezone(timezone.utc),
        )


@dataclass(frozen=True, slots=True)
class ResourceAdmission:
    outcome: AdmissionOutcome
    workload: WorkloadClass
    pressure: ResourcePressure
    reason_codes: tuple[str, ...]
    retryable: bool
    lease: ResourceLease | None = None

    def __post_init__(self) -> None:
        admitted = self.outcome is AdmissionOutcome.ADMITTED
        if admitted != (self.lease is not None):
            raise ValueError("Uma admissão aceita deve possuir exatamente uma licença.")
        if not self.reason_codes or len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes deve ser único e não vazio.")

    @property
    def admitted(self) -> bool:
        return self.outcome is AdmissionOutcome.ADMITTED


@dataclass(frozen=True, slots=True)
class ResourceManagerSnapshot:
    profile: RuntimeProfile
    support_status: RuntimeSupportStatus
    pressure: ResourcePressure
    pressure_reasons: tuple[str, ...]
    active_leases: int
    capacity: int
    metrics: RuntimeMetrics

    def public_summary(self) -> dict[str, object]:
        return {
            "profile": self.profile.value,
            "support_status": self.support_status.value,
            "pressure": self.pressure.value,
            "pressure_reasons": self.pressure_reasons,
            "active_leases": self.active_leases,
            "capacity": self.capacity,
            "cpu_percent": self.metrics.cpu_percent,
            "memory_percent": self.metrics.memory_percent,
            "available_memory_gb": round(self.metrics.available_memory_gb, 2),
            "process_rss_mb": (
                None
                if self.metrics.process_rss_mb is None
                else round(self.metrics.process_rss_mb, 2)
            ),
        }


@dataclass(frozen=True, slots=True)
class ResourceAuditEvent:
    event_id: str
    occurred_at: datetime
    action: ResourceAuditAction
    profile: RuntimeProfile
    workload: WorkloadClass
    pressure: ResourcePressure
    reason_codes: tuple[str, ...]
    active_leases: int
    lease_id: str | None = None


class InMemoryResourceAuditTrail:
    def __init__(
        self,
        *,
        max_events: int = 1000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (
            not isinstance(max_events, int)
            or isinstance(max_events, bool)
            or not 1 <= max_events <= 100_000
        ):
            raise ValueError("max_events deve estar entre 1 e 100000.")
        self._events: deque[ResourceAuditEvent] = deque(maxlen=max_events)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def append(
        self,
        *,
        action: ResourceAuditAction,
        profile: RuntimeProfile,
        workload: WorkloadClass,
        pressure: ResourcePressure,
        reason_codes: tuple[str, ...],
        active_leases: int,
        lease_id: str | None = None,
    ) -> ResourceAuditEvent:
        event = ResourceAuditEvent(
            event_id=uuid4().hex,
            occurred_at=self._clock().astimezone(timezone.utc),
            action=action,
            profile=profile,
            workload=workload,
            pressure=pressure,
            reason_codes=reason_codes,
            active_leases=active_leases,
            lease_id=lease_id,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list_events(self) -> tuple[ResourceAuditEvent, ...]:
        with self._lock:
            return tuple(self._events)


class RuntimeMetricsProbeError(RuntimeError):
    """Falha na leitura essencial da memória do sistema."""


class SystemRuntimeMetricsProbe:
    """Mede o sistema e somente o processo atual, sem enumerar terceiros."""

    def __init__(
        self,
        *,
        cpu_reader: Callable[[], float] | None = None,
        memory_reader: Callable[[], Any] | None = None,
        process_rss_reader: Callable[[], float] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cpu_reader = cpu_reader or (
            lambda: float(psutil.cpu_percent(interval=None))
        )
        self._memory_reader = memory_reader or psutil.virtual_memory
        self._process_rss_reader = process_rss_reader or self._read_process_rss
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def capture(self) -> RuntimeMetrics:
        try:
            memory = self._memory_reader()
            memory_percent = float(memory.percent)
            available_memory_gb = float(memory.available) / GIB
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            raise RuntimeMetricsProbeError(
                "Não foi possível medir a memória do sistema."
            ) from exc

        cpu_percent = self._optional_metric(self._cpu_reader)
        process_rss_mb = self._optional_metric(self._process_rss_reader)

        return RuntimeMetrics(
            captured_at=self._clock(),
            cpu_percent=(
                cpu_percent
                if cpu_percent is not None and cpu_percent <= 100
                else None
            ),
            memory_percent=memory_percent,
            available_memory_gb=available_memory_gb,
            process_rss_mb=process_rss_mb,
        )

    @staticmethod
    def _optional_metric(reader: Callable[[], float]) -> float | None:
        try:
            value = reader()
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(float(value))
                or value < 0
            ):
                return None
            return float(value)
        except (OSError, RuntimeError, TypeError, ValueError, psutil.Error):
            return None

    @staticmethod
    def _read_process_rss() -> float:
        return float(psutil.Process().memory_info().rss) / MIB


class ResourceAdmissionError(RuntimeError):
    def __init__(self, admission: ResourceAdmission) -> None:
        self.admission = admission
        super().__init__(
            "O Resource Manager não admitiu a carga: "
            + ", ".join(admission.reason_codes)
        )


class ResourceManager:
    def __init__(
        self,
        *,
        profile: RuntimeProfileDecision,
        metrics_probe: SystemRuntimeMetricsProbe | None = None,
        thresholds: ResourceThresholds | None = None,
        audit: InMemoryResourceAuditTrail | None = None,
    ) -> None:
        self.profile = profile
        self._probe = metrics_probe or SystemRuntimeMetricsProbe()
        self._thresholds = thresholds or ResourceThresholds()
        self._audit = audit or InMemoryResourceAuditTrail()
        self._active: dict[str, ResourceLease] = {}
        self._lock = RLock()

    @property
    def capacity(self) -> int:
        return self.profile.budget.parallel_task_limit

    @property
    def active_lease_count(self) -> int:
        with self._lock:
            return len(self._active)

    def assess_pressure(self, metrics: RuntimeMetrics) -> PressureAssessment:
        critical: list[str] = []
        warning: list[str] = []
        if (
            metrics.process_rss_mb is not None
            and metrics.process_rss_mb > self.profile.budget.memory_soft_limit_mb
        ):
            critical.append("process_memory_soft_limit_exceeded")
        if (
            metrics.available_memory_gb
            <= self._thresholds.critical_available_memory_gb
        ):
            critical.append("available_memory_critical")
        elif (
            metrics.available_memory_gb
            <= self._thresholds.warning_available_memory_gb
        ):
            warning.append("available_memory_warning")
        if metrics.memory_percent >= self._thresholds.critical_memory_percent:
            critical.append("system_memory_critical")
        elif metrics.memory_percent >= self._thresholds.warning_memory_percent:
            warning.append("system_memory_warning")
        if metrics.cpu_percent is not None:
            if metrics.cpu_percent >= self._thresholds.critical_cpu_percent:
                critical.append("cpu_critical")
            elif metrics.cpu_percent >= self._thresholds.warning_cpu_percent:
                warning.append("cpu_warning")
        if critical:
            return PressureAssessment(
                ResourcePressure.CRITICAL,
                tuple(critical + warning),
            )
        if warning:
            return PressureAssessment(ResourcePressure.WARNING, tuple(warning))
        return PressureAssessment(ResourcePressure.NORMAL, ("resources_available",))

    def status(self) -> ResourceManagerSnapshot:
        metrics = self._probe.capture()
        assessment = self.assess_pressure(metrics)
        return ResourceManagerSnapshot(
            profile=self.profile.selected,
            support_status=self.profile.support_status,
            pressure=assessment.pressure,
            pressure_reasons=assessment.reason_codes,
            active_leases=self.active_lease_count,
            capacity=self.capacity,
            metrics=metrics,
        )

    def try_acquire(self, workload: WorkloadClass) -> ResourceAdmission:
        if not isinstance(workload, WorkloadClass):
            raise TypeError("workload deve ser WorkloadClass.")
        try:
            metrics = self._probe.capture()
        except RuntimeMetricsProbeError:
            admission = ResourceAdmission(
                outcome=AdmissionOutcome.REJECTED_METRICS,
                workload=workload,
                pressure=ResourcePressure.CRITICAL,
                reason_codes=("essential_memory_metric_unavailable",),
                retryable=True,
            )
            with self._lock:
                self._audit_event(
                    ResourceAuditAction.REJECTED,
                    admission,
                    active_leases=len(self._active),
                )
            return admission
        assessment = self.assess_pressure(metrics)

        with self._lock:
            outcome, reasons = self._admission_outcome(workload, assessment)
            if outcome is not AdmissionOutcome.ADMITTED:
                admission = ResourceAdmission(
                    outcome=outcome,
                    workload=workload,
                    pressure=assessment.pressure,
                    reason_codes=reasons,
                    retryable=(
                        outcome is not AdmissionOutcome.REJECTED_UNSUPPORTED
                    ),
                )
                self._audit_event(
                    ResourceAuditAction.REJECTED,
                    admission,
                    active_leases=len(self._active),
                )
                return admission

            lease = ResourceLease(
                lease_id=uuid4().hex,
                workload=workload,
                acquired_at=metrics.captured_at,
            )
            self._active[lease.lease_id] = lease
            admission = ResourceAdmission(
                outcome=AdmissionOutcome.ADMITTED,
                workload=workload,
                pressure=assessment.pressure,
                reason_codes=reasons,
                retryable=False,
                lease=lease,
            )
            self._audit_event(
                ResourceAuditAction.ADMITTED,
                admission,
                active_leases=len(self._active),
            )
            return admission

    def _admission_outcome(
        self,
        workload: WorkloadClass,
        assessment: PressureAssessment,
    ) -> tuple[AdmissionOutcome, tuple[str, ...]]:
        if (
            self.profile.support_status is RuntimeSupportStatus.UNSUPPORTED
            and workload is not WorkloadClass.LIGHT
        ):
            return AdmissionOutcome.REJECTED_UNSUPPORTED, (
                "hardware_below_minimum",
            )
        if (
            assessment.pressure is ResourcePressure.CRITICAL
            and workload is not WorkloadClass.LIGHT
        ):
            return AdmissionOutcome.REJECTED_PRESSURE, assessment.reason_codes
        if (
            assessment.pressure is ResourcePressure.WARNING
            and workload is WorkloadClass.HEAVY
        ):
            return AdmissionOutcome.REJECTED_PRESSURE, assessment.reason_codes
        if len(self._active) >= self.capacity:
            return AdmissionOutcome.REJECTED_CAPACITY, (
                "parallel_task_limit_reached",
            )
        return AdmissionOutcome.ADMITTED, (
            "admission_granted",
            *assessment.reason_codes,
        )

    def release(self, lease_id: str) -> bool:
        if not isinstance(lease_id, str) or not _LEASE_ID.fullmatch(lease_id):
            raise ValueError("lease_id é inválido.")
        with self._lock:
            lease = self._active.pop(lease_id, None)
            if lease is None:
                return False
            admission = ResourceAdmission(
                outcome=AdmissionOutcome.ADMITTED,
                workload=lease.workload,
                pressure=ResourcePressure.NORMAL,
                reason_codes=("lease_released",),
                retryable=False,
                lease=lease,
            )
            self._audit_event(
                ResourceAuditAction.RELEASED,
                admission,
                active_leases=len(self._active),
            )
            return True

    @contextmanager
    def reserve(self, workload: WorkloadClass) -> Iterator[ResourceLease]:
        admission = self.try_acquire(workload)
        if not admission.admitted or admission.lease is None:
            raise ResourceAdmissionError(admission)
        try:
            yield admission.lease
        finally:
            self.release(admission.lease.lease_id)

    def audit_events(self) -> tuple[ResourceAuditEvent, ...]:
        return self._audit.list_events()

    def _audit_event(
        self,
        action: ResourceAuditAction,
        admission: ResourceAdmission,
        *,
        active_leases: int,
    ) -> None:
        self._audit.append(
            action=action,
            profile=self.profile.selected,
            workload=admission.workload,
            pressure=admission.pressure,
            reason_codes=admission.reason_codes,
            active_leases=active_leases,
            lease_id=(
                admission.lease.lease_id if admission.lease is not None else None
            ),
        )


__all__ = [
    "AdmissionOutcome",
    "InMemoryResourceAuditTrail",
    "PressureAssessment",
    "ResourceAdmission",
    "ResourceAdmissionError",
    "ResourceAuditAction",
    "ResourceAuditEvent",
    "ResourceLease",
    "ResourceManager",
    "ResourceManagerSnapshot",
    "ResourcePressure",
    "ResourceThresholds",
    "RuntimeMetrics",
    "RuntimeMetricsProbeError",
    "SystemRuntimeMetricsProbe",
    "WorkloadClass",
]
