from __future__ import annotations

from datetime import datetime, timezone
from math import inf, nan
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas.core.runtime_profile import (
    GIB,
    PROFILE_BUDGETS,
    HardwareSnapshot,
    ResourceProbeError,
    RuntimeProfile,
    RuntimeProfileSelector,
    RuntimeProfileService,
    RuntimeSupportStatus,
    SystemResourceProbe,
    parse_runtime_profile,
)


NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def snapshot(
    *,
    total: float = 16.0,
    available: float = 8.0,
    logical: int = 8,
    physical: int | None = 4,
    disk: float | None = 100.0,
    gpu: float | None = None,
) -> HardwareSnapshot:
    return HardwareSnapshot(
        captured_at=NOW,
        total_memory_gb=total,
        available_memory_gb=available,
        logical_cpus=logical,
        physical_cpus=physical,
        disk_free_gb=disk,
        gpu_vram_gb=gpu,
    )


@pytest.mark.parametrize(
    ("total", "logical", "expected"),
    [
        (7.0, 2, RuntimeProfile.LITE),
        (13.99, 16, RuntimeProfile.LITE),
        (14.0, 4, RuntimeProfile.STANDARD),
        (28.0, 8, RuntimeProfile.FULL),
    ],
)
def test_auto_profile_uses_stable_hardware_thresholds(
    total: float,
    logical: int,
    expected: RuntimeProfile,
) -> None:
    available = min(total, 4.0)
    decision = RuntimeProfileSelector().select(
        snapshot(
            total=total,
            available=available,
            logical=logical,
            physical=min(logical, 4),
        )
    )

    assert decision.selected is expected
    assert decision.recommended is expected
    assert decision.requested is RuntimeProfile.AUTO
    assert decision.fallback_applied is False
    assert "automatic_profile_selected" in decision.reason_codes


def test_full_profile_requires_enough_free_disk_when_measurement_exists() -> None:
    decision = RuntimeProfileSelector().select(
        snapshot(total=32, available=20, logical=16, physical=8, disk=19.99)
    )

    assert decision.selected is RuntimeProfile.STANDARD


def test_missing_disk_measurement_does_not_invent_a_failure() -> None:
    decision = RuntimeProfileSelector().select(
        snapshot(total=32, available=20, logical=16, physical=8, disk=None)
    )

    assert decision.selected is RuntimeProfile.FULL
    assert decision.support_status is RuntimeSupportStatus.SUPPORTED


def test_machine_below_8gb_class_is_explicitly_unsupported() -> None:
    decision = RuntimeProfileSelector().select(
        snapshot(total=6.99, available=4, logical=4, physical=2)
    )

    assert decision.selected is RuntimeProfile.LITE
    assert decision.support_status is RuntimeSupportStatus.UNSUPPORTED
    assert "memory_below_8gb_class" in decision.reason_codes


def test_machine_below_two_logical_cpus_is_explicitly_unsupported() -> None:
    decision = RuntimeProfileSelector().select(
        snapshot(total=8, available=4, logical=1, physical=1)
    )

    assert decision.support_status is RuntimeSupportStatus.UNSUPPORTED
    assert "cpu_below_minimum" in decision.reason_codes


@pytest.mark.parametrize(
    ("available", "disk", "reason"),
    [
        (0.99, 50.0, "available_memory_low"),
        (4.0, 1.99, "disk_space_low"),
    ],
)
def test_temporary_resource_pressure_marks_profile_limited(
    available: float,
    disk: float,
    reason: str,
) -> None:
    decision = RuntimeProfileSelector().select(
        snapshot(available=available, disk=disk)
    )

    assert decision.support_status is RuntimeSupportStatus.LIMITED
    assert reason in decision.reason_codes


def test_explicit_lower_profile_is_respected() -> None:
    decision = RuntimeProfileSelector().select(
        snapshot(total=32, available=20, logical=16, physical=8),
        " LITE ",
    )

    assert decision.recommended is RuntimeProfile.FULL
    assert decision.selected is RuntimeProfile.LITE
    assert decision.fallback_applied is False
    assert "requested_profile_supported" in decision.reason_codes


def test_incompatible_explicit_profile_is_reduced_transparently() -> None:
    decision = RuntimeProfileSelector().select(
        snapshot(total=8, available=4, logical=4, physical=2),
        RuntimeProfile.FULL,
    )

    assert decision.selected is RuntimeProfile.LITE
    assert decision.fallback_applied is True
    assert "requested_profile_reduced" in decision.reason_codes


@pytest.mark.parametrize(
    ("profile", "workers", "parallel", "memory", "context", "lazy"),
    [
        (RuntimeProfile.LITE, 1, 1, 2048, 4096, True),
        (RuntimeProfile.STANDARD, 2, 2, 4096, 8192, True),
        (RuntimeProfile.FULL, 4, 4, 8192, 16384, False),
    ],
)
def test_each_profile_has_bounded_public_budget(
    profile: RuntimeProfile,
    workers: int,
    parallel: int,
    memory: int,
    context: int,
    lazy: bool,
) -> None:
    budget = PROFILE_BUDGETS[profile]

    assert budget.worker_limit == workers
    assert budget.parallel_task_limit == parallel
    assert budget.memory_soft_limit_mb == memory
    assert budget.model_context_limit == context
    assert budget.lazy_loading_preferred is lazy


@pytest.mark.parametrize("value", ["turbo", "", "automatic"])
def test_invalid_or_noncanonical_profile_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="Perfil inválido"):
        parse_runtime_profile(value)


def test_profile_parser_normalizes_case_and_outer_spaces() -> None:
    assert parse_runtime_profile(" FULL ") is RuntimeProfile.FULL


def test_non_text_profile_is_rejected() -> None:
    with pytest.raises(TypeError, match="texto ou RuntimeProfile"):
        parse_runtime_profile(1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_memory_gb", 0),
        ("total_memory_gb", nan),
        ("available_memory_gb", -1),
        ("available_memory_gb", inf),
        ("disk_free_gb", -1),
        ("gpu_vram_gb", nan),
    ],
)
def test_snapshot_rejects_invalid_numeric_metrics(field: str, value: float) -> None:
    values = {
        "captured_at": NOW,
        "total_memory_gb": 16.0,
        "available_memory_gb": 8.0,
        "logical_cpus": 8,
        "physical_cpus": 4,
        "disk_free_gb": 100.0,
        "gpu_vram_gb": None,
    }
    values[field] = value

    with pytest.raises(ValueError):
        HardwareSnapshot(**values)  # type: ignore[arg-type]


def test_snapshot_rejects_more_available_than_total() -> None:
    with pytest.raises(ValueError, match="não pode superar"):
        snapshot(total=8, available=9)


@pytest.mark.parametrize(
    ("logical", "physical"),
    [(0, None), (True, None), (4, 0), (4, 5), (4, True)],
)
def test_snapshot_rejects_invalid_cpu_counts(
    logical: int,
    physical: int | None,
) -> None:
    with pytest.raises(ValueError):
        snapshot(logical=logical, physical=physical)


def test_snapshot_requires_timezone() -> None:
    with pytest.raises(ValueError, match="fuso horário"):
        HardwareSnapshot(
            captured_at=datetime(2026, 9, 3),
            total_memory_gb=16,
            available_memory_gb=8,
            logical_cpus=8,
            physical_cpus=4,
            disk_free_gb=100,
        )


def test_probe_collects_only_aggregate_metrics(tmp_path: Path) -> None:
    probe = SystemResourceProbe(
        project_root=tmp_path,
        memory_reader=lambda: SimpleNamespace(total=16 * GIB, available=6 * GIB),
        cpu_reader=lambda logical: 12 if logical else 6,
        disk_reader=lambda _path: SimpleNamespace(free=80 * GIB),
        gpu_vram_reader=lambda: 8.0,
        clock=lambda: NOW,
    )

    measured = probe.capture()

    assert measured == snapshot(
        total=16,
        available=6,
        logical=12,
        physical=6,
        disk=80,
        gpu=8,
    )


def test_probe_handles_optional_measurement_failures(tmp_path: Path) -> None:
    def fail_disk(_path: Path) -> object:
        raise OSError("indisponível")

    def fail_gpu() -> float:
        raise RuntimeError("indisponível")

    probe = SystemResourceProbe(
        project_root=tmp_path,
        memory_reader=lambda: SimpleNamespace(total=8 * GIB, available=4 * GIB),
        cpu_reader=lambda _logical: None,
        disk_reader=fail_disk,
        gpu_vram_reader=fail_gpu,
        clock=lambda: NOW,
    )

    measured = probe.capture()

    assert measured.logical_cpus == 1
    assert measured.physical_cpus is None
    assert measured.disk_free_gb is None
    assert measured.gpu_vram_gb is None


@pytest.mark.parametrize("optional_value", [-1.0, inf, nan, True])
def test_probe_discards_invalid_optional_gpu_values(
    tmp_path: Path,
    optional_value: float,
) -> None:
    probe = SystemResourceProbe(
        project_root=tmp_path,
        memory_reader=lambda: SimpleNamespace(total=8 * GIB, available=4 * GIB),
        cpu_reader=lambda logical: 4 if logical else 2,
        disk_reader=lambda _path: SimpleNamespace(free=20 * GIB),
        gpu_vram_reader=lambda: optional_value,
        clock=lambda: NOW,
    )

    assert probe.capture().gpu_vram_gb is None


@pytest.mark.parametrize("optional_value", [-1.0, inf, nan])
def test_probe_discards_invalid_optional_disk_values(
    tmp_path: Path,
    optional_value: float,
) -> None:
    probe = SystemResourceProbe(
        project_root=tmp_path,
        memory_reader=lambda: SimpleNamespace(total=8 * GIB, available=4 * GIB),
        cpu_reader=lambda logical: 4 if logical else 2,
        disk_reader=lambda _path: SimpleNamespace(free=optional_value),
        clock=lambda: NOW,
    )

    assert probe.capture().disk_free_gb is None


def test_probe_rejects_missing_essential_memory_metrics(tmp_path: Path) -> None:
    probe = SystemResourceProbe(
        project_root=tmp_path,
        memory_reader=lambda: object(),
    )

    with pytest.raises(ResourceProbeError, match="medir a memória"):
        probe.capture()


def test_profile_service_combines_probe_and_selector(tmp_path: Path) -> None:
    probe = SystemResourceProbe(
        project_root=tmp_path,
        memory_reader=lambda: SimpleNamespace(total=16 * GIB, available=8 * GIB),
        cpu_reader=lambda logical: 8 if logical else 4,
        disk_reader=lambda _path: SimpleNamespace(free=100 * GIB),
        clock=lambda: NOW,
    )

    decision = RuntimeProfileService(
        project_root=tmp_path,
        probe=probe,
    ).resolve("standard")

    assert decision.selected is RuntimeProfile.STANDARD
    assert decision.support_status is RuntimeSupportStatus.SUPPORTED


def test_public_summary_does_not_expose_paths_or_identity() -> None:
    decision = RuntimeProfileSelector().select(snapshot(gpu=8.1234))

    summary = decision.public_summary()
    serialized = repr(summary).lower()

    assert summary["gpu_vram_gb"] == 8.12
    assert "path" not in serialized
    assert "user" not in serialized
    assert "process" not in serialized
    assert "serial" not in serialized


def test_decision_rejects_mismatched_budget() -> None:
    decision = RuntimeProfileSelector().select(snapshot())

    with pytest.raises(ValueError, match="orçamento"):
        type(decision)(
            requested=decision.requested,
            recommended=decision.recommended,
            selected=decision.selected,
            support_status=decision.support_status,
            fallback_applied=decision.fallback_applied,
            reason_codes=decision.reason_codes,
            snapshot=decision.snapshot,
            budget=PROFILE_BUDGETS[RuntimeProfile.LITE],
        )
