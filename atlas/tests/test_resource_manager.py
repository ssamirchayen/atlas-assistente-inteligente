from __future__ import annotations

from datetime import datetime, timezone
from math import inf, nan
from threading import Barrier, Thread
from types import SimpleNamespace

import pytest

from atlas.core.resource_manager import (
    AdmissionOutcome,
    InMemoryResourceAuditTrail,
    ResourceAdmissionError,
    ResourceAuditAction,
    ResourceManager,
    ResourcePressure,
    ResourceThresholds,
    RuntimeMetrics,
    RuntimeMetricsProbeError,
    SystemRuntimeMetricsProbe,
    WorkloadClass,
)
from atlas.core.runtime_profile import (
    GIB,
    HardwareSnapshot,
    RuntimeProfileSelector,
)


NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def runtime_profile(
    *,
    total_memory_gb: float = 16,
    logical_cpus: int = 8,
):
    hardware = HardwareSnapshot(
        captured_at=NOW,
        total_memory_gb=total_memory_gb,
        available_memory_gb=min(8, total_memory_gb),
        logical_cpus=logical_cpus,
        physical_cpus=min(4, logical_cpus),
        disk_free_gb=100,
    )
    return RuntimeProfileSelector().select(hardware)


def metrics(
    *,
    cpu: float | None = 20,
    memory: float = 40,
    available: float = 8,
    rss: float | None = 300,
) -> RuntimeMetrics:
    return RuntimeMetrics(
        captured_at=NOW,
        cpu_percent=cpu,
        memory_percent=memory,
        available_memory_gb=available,
        process_rss_mb=rss,
    )


class FixedProbe:
    def __init__(self, value: RuntimeMetrics) -> None:
        self.value = value
        self.calls = 0

    def capture(self) -> RuntimeMetrics:
        self.calls += 1
        return self.value


def manager(
    value: RuntimeMetrics | None = None,
    *,
    total_memory_gb: float = 16,
    logical_cpus: int = 8,
    audit: InMemoryResourceAuditTrail | None = None,
) -> ResourceManager:
    return ResourceManager(
        profile=runtime_profile(
            total_memory_gb=total_memory_gb,
            logical_cpus=logical_cpus,
        ),
        metrics_probe=FixedProbe(value or metrics()),  # type: ignore[arg-type]
        audit=audit,
    )


@pytest.mark.parametrize(
    ("value", "expected", "reason"),
    [
        (metrics(), ResourcePressure.NORMAL, "resources_available"),
        (
            metrics(cpu=90),
            ResourcePressure.WARNING,
            "cpu_warning",
        ),
        (
            metrics(cpu=98),
            ResourcePressure.CRITICAL,
            "cpu_critical",
        ),
        (
            metrics(memory=85),
            ResourcePressure.WARNING,
            "system_memory_warning",
        ),
        (
            metrics(memory=95),
            ResourcePressure.CRITICAL,
            "system_memory_critical",
        ),
        (
            metrics(available=1.5),
            ResourcePressure.WARNING,
            "available_memory_warning",
        ),
        (
            metrics(available=0.5),
            ResourcePressure.CRITICAL,
            "available_memory_critical",
        ),
        (
            metrics(rss=4097),
            ResourcePressure.CRITICAL,
            "process_memory_soft_limit_exceeded",
        ),
    ],
)
def test_pressure_assessment_has_stable_thresholds(
    value: RuntimeMetrics,
    expected: ResourcePressure,
    reason: str,
) -> None:
    assessment = manager().assess_pressure(value)

    assert assessment.pressure is expected
    assert reason in assessment.reason_codes


def test_normal_workload_is_admitted_and_released() -> None:
    resource_manager = manager()

    admission = resource_manager.try_acquire(WorkloadClass.STANDARD)

    assert admission.admitted is True
    assert admission.lease is not None
    assert resource_manager.active_lease_count == 1
    assert resource_manager.release(admission.lease.lease_id) is True
    assert resource_manager.release(admission.lease.lease_id) is False
    assert resource_manager.active_lease_count == 0


def test_context_manager_releases_lease_after_success() -> None:
    resource_manager = manager()

    with resource_manager.reserve(WorkloadClass.STANDARD) as lease:
        assert lease.workload is WorkloadClass.STANDARD
        assert resource_manager.active_lease_count == 1

    assert resource_manager.active_lease_count == 0


def test_context_manager_releases_lease_after_failure() -> None:
    resource_manager = manager()

    with pytest.raises(RuntimeError, match="falha simulada"):
        with resource_manager.reserve(WorkloadClass.STANDARD):
            raise RuntimeError("falha simulada")

    assert resource_manager.active_lease_count == 0


def test_standard_profile_enforces_parallel_capacity() -> None:
    resource_manager = manager()
    first = resource_manager.try_acquire(WorkloadClass.STANDARD)
    second = resource_manager.try_acquire(WorkloadClass.STANDARD)
    third = resource_manager.try_acquire(WorkloadClass.STANDARD)

    assert first.admitted and second.admitted
    assert third.outcome is AdmissionOutcome.REJECTED_CAPACITY
    assert third.retryable is True
    assert "parallel_task_limit_reached" in third.reason_codes


def test_capacity_check_is_thread_safe() -> None:
    resource_manager = manager(total_memory_gb=8, logical_cpus=4)
    barrier = Barrier(5)
    admissions = []

    def acquire() -> None:
        barrier.wait()
        admissions.append(resource_manager.try_acquire(WorkloadClass.STANDARD))

    threads = [Thread(target=acquire) for _ in range(4)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert sum(item.admitted for item in admissions) == 1
    assert resource_manager.active_lease_count == 1


def test_warning_pressure_blocks_only_heavy_workload() -> None:
    resource_manager = manager(metrics(cpu=92))

    heavy = resource_manager.try_acquire(WorkloadClass.HEAVY)
    standard = resource_manager.try_acquire(WorkloadClass.STANDARD)

    assert heavy.outcome is AdmissionOutcome.REJECTED_PRESSURE
    assert standard.admitted is True


def test_critical_pressure_preserves_only_light_workload() -> None:
    resource_manager = manager(metrics(memory=97, available=0.3))

    standard = resource_manager.try_acquire(WorkloadClass.STANDARD)
    light = resource_manager.try_acquire(WorkloadClass.LIGHT)

    assert standard.outcome is AdmissionOutcome.REJECTED_PRESSURE
    assert light.admitted is True
    assert light.pressure is ResourcePressure.CRITICAL


def test_unsupported_hardware_preserves_only_light_workload() -> None:
    resource_manager = manager(total_memory_gb=6, logical_cpus=4)

    standard = resource_manager.try_acquire(WorkloadClass.STANDARD)
    light = resource_manager.try_acquire(WorkloadClass.LIGHT)

    assert standard.outcome is AdmissionOutcome.REJECTED_UNSUPPORTED
    assert standard.retryable is False
    assert light.admitted is True


def test_rejected_reservation_raises_structured_error() -> None:
    resource_manager = manager(metrics(cpu=99))

    with pytest.raises(ResourceAdmissionError) as captured:
        with resource_manager.reserve(WorkloadClass.HEAVY):
            pytest.fail("a carga não poderia ser admitida")

    assert captured.value.admission.outcome is AdmissionOutcome.REJECTED_PRESSURE


def test_status_contains_only_aggregate_metrics() -> None:
    summary = manager().status().public_summary()
    serialized = repr(summary).lower()

    assert summary["profile"] == "standard"
    assert summary["capacity"] == 2
    assert "path" not in serialized
    assert "user" not in serialized
    assert "process_name" not in serialized
    assert "serial" not in serialized


def test_audit_is_bounded_and_contains_no_payload() -> None:
    audit = InMemoryResourceAuditTrail(max_events=2, clock=lambda: NOW)
    resource_manager = manager(audit=audit)

    first = resource_manager.try_acquire(WorkloadClass.STANDARD)
    assert first.lease is not None
    resource_manager.release(first.lease.lease_id)
    resource_manager.try_acquire(WorkloadClass.STANDARD)

    events = resource_manager.audit_events()
    assert len(events) == 2
    assert events[0].action is ResourceAuditAction.RELEASED
    assert not hasattr(events[0], "payload")
    assert not hasattr(events[0], "command")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cpu_percent", -1),
        ("cpu_percent", 101),
        ("memory_percent", nan),
        ("memory_percent", 101),
        ("available_memory_gb", -1),
        ("process_rss_mb", inf),
    ],
)
def test_runtime_metrics_reject_invalid_values(field: str, value: float) -> None:
    values = {
        "captured_at": NOW,
        "cpu_percent": 20,
        "memory_percent": 40,
        "available_memory_gb": 8,
        "process_rss_mb": 300,
    }
    values[field] = value

    with pytest.raises(ValueError):
        RuntimeMetrics(**values)  # type: ignore[arg-type]


def test_thresholds_reject_inverted_limits() -> None:
    with pytest.raises(ValueError, match="crítico de CPU"):
        ResourceThresholds(warning_cpu_percent=99, critical_cpu_percent=98)
    with pytest.raises(ValueError, match="RAM disponível"):
        ResourceThresholds(
            warning_available_memory_gb=0.5,
            critical_available_memory_gb=1.0,
        )


def test_system_probe_collects_current_process_metrics_only() -> None:
    probe = SystemRuntimeMetricsProbe(
        cpu_reader=lambda: 25,
        memory_reader=lambda: SimpleNamespace(percent=50, available=4 * GIB),
        process_rss_reader=lambda: 256,
        clock=lambda: NOW,
    )

    assert probe.capture() == metrics(cpu=25, memory=50, available=4, rss=256)


@pytest.mark.parametrize("value", [-1, 101, inf, nan, True])
def test_system_probe_discards_invalid_optional_cpu(value: float) -> None:
    probe = SystemRuntimeMetricsProbe(
        cpu_reader=lambda: value,
        memory_reader=lambda: SimpleNamespace(percent=50, available=4 * GIB),
        process_rss_reader=lambda: 256,
        clock=lambda: NOW,
    )

    assert probe.capture().cpu_percent is None


def test_system_probe_fails_closed_without_memory() -> None:
    probe = SystemRuntimeMetricsProbe(memory_reader=lambda: object())

    with pytest.raises(RuntimeMetricsProbeError, match="medir a memória"):
        probe.capture()


def test_manager_returns_structured_rejection_without_memory_metrics() -> None:
    class FailingProbe:
        def capture(self) -> RuntimeMetrics:
            raise RuntimeMetricsProbeError("indisponível")

    resource_manager = ResourceManager(
        profile=runtime_profile(),
        metrics_probe=FailingProbe(),  # type: ignore[arg-type]
    )

    admission = resource_manager.try_acquire(WorkloadClass.STANDARD)

    assert admission.outcome is AdmissionOutcome.REJECTED_METRICS
    assert admission.pressure is ResourcePressure.CRITICAL
    assert admission.retryable is True
    assert admission.reason_codes == ("essential_memory_metric_unavailable",)
    assert resource_manager.active_lease_count == 0


def test_release_rejects_malformed_identifier() -> None:
    with pytest.raises(ValueError, match="lease_id"):
        manager().release("../lease")


def test_workload_requires_enum() -> None:
    with pytest.raises(TypeError, match="WorkloadClass"):
        manager().try_acquire("heavy")  # type: ignore[arg-type]
