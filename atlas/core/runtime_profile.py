"""Diagnóstico local e seleção transparente do perfil do Atlas Core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Any

import psutil


GIB = 1024**3
OBSERVED_8_GB_FLOOR = 7.0


class RuntimeProfile(StrEnum):
    AUTO = "auto"
    LITE = "lite"
    STANDARD = "standard"
    FULL = "full"


class RuntimeSupportStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class HardwareSnapshot:
    captured_at: datetime
    total_memory_gb: float
    available_memory_gb: float
    logical_cpus: int
    physical_cpus: int | None
    disk_free_gb: float | None
    gpu_vram_gb: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.captured_at, datetime) or self.captured_at.tzinfo is None:
            raise ValueError("captured_at deve possuir fuso horário.")
        object.__setattr__(
            self,
            "captured_at",
            self.captured_at.astimezone(timezone.utc),
        )
        self._positive_number("total_memory_gb", self.total_memory_gb)
        self._non_negative_number("available_memory_gb", self.available_memory_gb)
        if self.available_memory_gb > self.total_memory_gb:
            raise ValueError("available_memory_gb não pode superar total_memory_gb.")
        if (
            not isinstance(self.logical_cpus, int)
            or isinstance(self.logical_cpus, bool)
            or self.logical_cpus < 1
        ):
            raise ValueError("logical_cpus deve ser inteiro positivo.")
        if self.physical_cpus is not None and (
            not isinstance(self.physical_cpus, int)
            or isinstance(self.physical_cpus, bool)
            or self.physical_cpus < 1
            or self.physical_cpus > self.logical_cpus
        ):
            raise ValueError("physical_cpus é inválido.")
        for field_name in ("disk_free_gb", "gpu_vram_gb"):
            value = getattr(self, field_name)
            if value is not None:
                self._non_negative_number(field_name, value)

    @staticmethod
    def _positive_number(label: str, value: float) -> None:
        HardwareSnapshot._non_negative_number(label, value)
        if value <= 0:
            raise ValueError(f"{label} deve ser positivo.")

    @staticmethod
    def _non_negative_number(label: str, value: float) -> None:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
            or value < 0
        ):
            raise ValueError(f"{label} deve ser número finito não negativo.")


@dataclass(frozen=True, slots=True)
class RuntimeBudget:
    profile: RuntimeProfile
    worker_limit: int
    parallel_task_limit: int
    memory_soft_limit_mb: int
    model_context_limit: int
    lazy_loading_preferred: bool

    def __post_init__(self) -> None:
        if self.profile is RuntimeProfile.AUTO:
            raise ValueError("RuntimeBudget exige perfil concreto.")
        for field_name in (
            "worker_limit",
            "parallel_task_limit",
            "memory_soft_limit_mb",
            "model_context_limit",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{field_name} deve ser inteiro positivo.")


PROFILE_BUDGETS = {
    RuntimeProfile.LITE: RuntimeBudget(
        profile=RuntimeProfile.LITE,
        worker_limit=1,
        parallel_task_limit=1,
        memory_soft_limit_mb=2048,
        model_context_limit=4096,
        lazy_loading_preferred=True,
    ),
    RuntimeProfile.STANDARD: RuntimeBudget(
        profile=RuntimeProfile.STANDARD,
        worker_limit=2,
        parallel_task_limit=2,
        memory_soft_limit_mb=4096,
        model_context_limit=8192,
        lazy_loading_preferred=True,
    ),
    RuntimeProfile.FULL: RuntimeBudget(
        profile=RuntimeProfile.FULL,
        worker_limit=4,
        parallel_task_limit=4,
        memory_soft_limit_mb=8192,
        model_context_limit=16384,
        lazy_loading_preferred=False,
    ),
}


@dataclass(frozen=True, slots=True)
class RuntimeProfileDecision:
    requested: RuntimeProfile
    recommended: RuntimeProfile
    selected: RuntimeProfile
    support_status: RuntimeSupportStatus
    fallback_applied: bool
    reason_codes: tuple[str, ...]
    snapshot: HardwareSnapshot
    budget: RuntimeBudget

    def __post_init__(self) -> None:
        if self.recommended is RuntimeProfile.AUTO or self.selected is RuntimeProfile.AUTO:
            raise ValueError("recommended e selected exigem perfis concretos.")
        if self.budget.profile is not self.selected:
            raise ValueError("O orçamento deve corresponder ao perfil selecionado.")
        if not self.reason_codes or len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes deve ser único e não vazio.")

    def public_summary(self) -> dict[str, object]:
        """Retorna somente métricas agregadas, sem identidade ou caminhos."""

        return {
            "requested": self.requested.value,
            "recommended": self.recommended.value,
            "selected": self.selected.value,
            "support_status": self.support_status.value,
            "fallback_applied": self.fallback_applied,
            "reason_codes": self.reason_codes,
            "total_memory_gb": round(self.snapshot.total_memory_gb, 2),
            "available_memory_gb": round(self.snapshot.available_memory_gb, 2),
            "logical_cpus": self.snapshot.logical_cpus,
            "physical_cpus": self.snapshot.physical_cpus,
            "disk_free_gb": (
                None
                if self.snapshot.disk_free_gb is None
                else round(self.snapshot.disk_free_gb, 2)
            ),
            "gpu_vram_gb": (
                None
                if self.snapshot.gpu_vram_gb is None
                else round(self.snapshot.gpu_vram_gb, 2)
            ),
        }


def parse_runtime_profile(value: RuntimeProfile | str) -> RuntimeProfile:
    if isinstance(value, RuntimeProfile):
        return value
    if not isinstance(value, str):
        raise TypeError("O perfil solicitado deve ser texto ou RuntimeProfile.")
    try:
        return RuntimeProfile(value.strip().lower())
    except ValueError as exc:
        raise ValueError("Perfil inválido; use auto, lite, standard ou full.") from exc


class RuntimeProfileSelector:
    """Seleciona um perfil sem ocultar reduções ou limitações do equipamento."""

    _rank = {
        RuntimeProfile.LITE: 1,
        RuntimeProfile.STANDARD: 2,
        RuntimeProfile.FULL: 3,
    }

    def select(
        self,
        snapshot: HardwareSnapshot,
        requested: RuntimeProfile | str = RuntimeProfile.AUTO,
    ) -> RuntimeProfileDecision:
        requested_profile = parse_runtime_profile(requested)
        recommended = self._recommend(snapshot)
        support_status, support_reasons = self._support(snapshot)
        reasons = list(support_reasons)

        if requested_profile is RuntimeProfile.AUTO:
            selected = recommended
            fallback_applied = False
            reasons.append("automatic_profile_selected")
        elif self._rank[requested_profile] <= self._rank[recommended]:
            selected = requested_profile
            fallback_applied = False
            reasons.append("requested_profile_supported")
        else:
            selected = recommended
            fallback_applied = True
            reasons.append("requested_profile_reduced")

        return RuntimeProfileDecision(
            requested=requested_profile,
            recommended=recommended,
            selected=selected,
            support_status=support_status,
            fallback_applied=fallback_applied,
            reason_codes=tuple(dict.fromkeys(reasons)),
            snapshot=snapshot,
            budget=PROFILE_BUDGETS[selected],
        )

    @staticmethod
    def _recommend(snapshot: HardwareSnapshot) -> RuntimeProfile:
        disk_allows_full = (
            snapshot.disk_free_gb is None or snapshot.disk_free_gb >= 20.0
        )
        if (
            snapshot.total_memory_gb >= 28.0
            and snapshot.logical_cpus >= 8
            and disk_allows_full
        ):
            return RuntimeProfile.FULL
        if snapshot.total_memory_gb >= 14.0 and snapshot.logical_cpus >= 4:
            return RuntimeProfile.STANDARD
        return RuntimeProfile.LITE

    @staticmethod
    def _support(
        snapshot: HardwareSnapshot,
    ) -> tuple[RuntimeSupportStatus, tuple[str, ...]]:
        reasons: list[str] = []
        if snapshot.total_memory_gb < OBSERVED_8_GB_FLOOR:
            reasons.append("memory_below_8gb_class")
            return RuntimeSupportStatus.UNSUPPORTED, tuple(reasons)
        if snapshot.logical_cpus < 2:
            reasons.append("cpu_below_minimum")
            return RuntimeSupportStatus.UNSUPPORTED, tuple(reasons)
        if snapshot.available_memory_gb < 1.0:
            reasons.append("available_memory_low")
        if snapshot.disk_free_gb is not None and snapshot.disk_free_gb < 2.0:
            reasons.append("disk_space_low")
        if reasons:
            return RuntimeSupportStatus.LIMITED, tuple(reasons)
        return RuntimeSupportStatus.SUPPORTED, ("minimum_requirements_met",)


class ResourceProbeError(RuntimeError):
    """Falha ao obter a única métrica essencial: memória total."""


class SystemResourceProbe:
    """Coleta métricas agregadas sem enumerar processos, arquivos ou identidade."""

    def __init__(
        self,
        *,
        project_root: Path,
        memory_reader: Callable[[], Any] | None = None,
        cpu_reader: Callable[[bool], int | None] | None = None,
        disk_reader: Callable[[Path], Any] | None = None,
        gpu_vram_reader: Callable[[], float | None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._project_root = Path(project_root).resolve()
        self._memory_reader = memory_reader or psutil.virtual_memory
        self._cpu_reader = cpu_reader or (
            lambda logical: psutil.cpu_count(logical=logical)
        )
        self._disk_reader = disk_reader or psutil.disk_usage
        self._gpu_vram_reader = gpu_vram_reader
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def capture(self) -> HardwareSnapshot:
        try:
            memory = self._memory_reader()
            total_memory_gb = float(memory.total) / GIB
            available_memory_gb = float(memory.available) / GIB
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            raise ResourceProbeError("Não foi possível medir a memória do sistema.") from exc

        logical_cpus = self._safe_cpu_count(logical=True) or 1
        physical_cpus = self._safe_cpu_count(logical=False)
        if physical_cpus is not None and physical_cpus > logical_cpus:
            physical_cpus = None

        disk_free_gb: float | None
        try:
            disk_free_gb = float(self._disk_reader(self._project_root).free) / GIB
            if not isfinite(disk_free_gb) or disk_free_gb < 0:
                disk_free_gb = None
        except (AttributeError, OSError, TypeError, ValueError):
            disk_free_gb = None

        gpu_vram_gb: float | None = None
        if self._gpu_vram_reader is not None:
            try:
                gpu_vram_gb = self._gpu_vram_reader()
                if (
                    gpu_vram_gb is not None
                    and (
                        not isinstance(gpu_vram_gb, (int, float))
                        or isinstance(gpu_vram_gb, bool)
                        or not isfinite(float(gpu_vram_gb))
                        or gpu_vram_gb < 0
                    )
                ):
                    gpu_vram_gb = None
            except (OSError, RuntimeError, TypeError, ValueError):
                gpu_vram_gb = None

        return HardwareSnapshot(
            captured_at=self._clock(),
            total_memory_gb=total_memory_gb,
            available_memory_gb=available_memory_gb,
            logical_cpus=logical_cpus,
            physical_cpus=physical_cpus,
            disk_free_gb=disk_free_gb,
            gpu_vram_gb=gpu_vram_gb,
        )

    def _safe_cpu_count(self, *, logical: bool) -> int | None:
        try:
            value = self._cpu_reader(logical)
        except (OSError, TypeError, ValueError):
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            return None
        return value


class RuntimeProfileService:
    def __init__(
        self,
        *,
        project_root: Path,
        probe: SystemResourceProbe | None = None,
        selector: RuntimeProfileSelector | None = None,
    ) -> None:
        self._probe = probe or SystemResourceProbe(project_root=project_root)
        self._selector = selector or RuntimeProfileSelector()

    def resolve(
        self,
        requested: RuntimeProfile | str = RuntimeProfile.AUTO,
    ) -> RuntimeProfileDecision:
        return self._selector.select(self._probe.capture(), requested)


__all__ = [
    "HardwareSnapshot",
    "OBSERVED_8_GB_FLOOR",
    "PROFILE_BUDGETS",
    "ResourceProbeError",
    "RuntimeBudget",
    "RuntimeProfile",
    "RuntimeProfileDecision",
    "RuntimeProfileSelector",
    "RuntimeProfileService",
    "RuntimeSupportStatus",
    "SystemResourceProbe",
    "parse_runtime_profile",
]
