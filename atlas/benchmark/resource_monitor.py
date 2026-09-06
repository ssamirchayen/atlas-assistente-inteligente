"""Low-overhead resource monitoring for Atlas benchmark cases.

CPU/RAM are collected with psutil when available. NVIDIA GPU metrics are
optional and discovered via ``nvidia-smi`` so the benchmark does not require a
new hard dependency. GPU values represent the active GPU as a whole, which is
important for Atlas because Ollama may own the VRAM rather than Atlas.exe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from statistics import fmean
from typing import Protocol

from .metrics import percentile


@dataclass(frozen=True, slots=True)
class ResourceSample:
    """One timestamped system/process resource sample."""

    timestamp: float
    process_cpu_percent: float | None = None
    process_rss_mb: float | None = None
    system_cpu_percent: float | None = None
    system_memory_percent: float | None = None
    gpu_util_percent: float | None = None
    gpu_vram_used_mb: float | None = None
    gpu_vram_total_mb: float | None = None


class ResourceSampler(Protocol):
    """Sampler contract used by :class:`SystemResourceMonitor`."""

    def sample(self, *, include_gpu: bool = True) -> ResourceSample: ...


@dataclass(frozen=True, slots=True)
class ResourceSummary:
    """Aggregated resources for one benchmark case."""

    sample_count: int
    process_cpu_mean_pct: float | None = None
    process_cpu_p95_pct: float | None = None
    process_cpu_peak_pct: float | None = None
    process_rss_mean_mb: float | None = None
    process_rss_peak_mb: float | None = None
    system_cpu_mean_pct: float | None = None
    system_cpu_peak_pct: float | None = None
    system_memory_mean_pct: float | None = None
    system_memory_peak_pct: float | None = None
    gpu_util_mean_pct: float | None = None
    gpu_util_peak_pct: float | None = None
    gpu_vram_mean_mb: float | None = None
    gpu_vram_peak_mb: float | None = None
    gpu_vram_total_mb: float | None = None

    @classmethod
    def from_samples(cls, samples: list[ResourceSample]) -> "ResourceSummary":
        def values(name: str) -> list[float]:
            collected: list[float] = []
            for sample in samples:
                value = getattr(sample, name)
                if value is not None:
                    collected.append(float(value))
            return collected

        def mean_or_none(items: list[float]) -> float | None:
            return round(fmean(items), 3) if items else None

        def peak_or_none(items: list[float]) -> float | None:
            return round(max(items), 3) if items else None

        process_cpu = values("process_cpu_percent")
        process_rss = values("process_rss_mb")
        system_cpu = values("system_cpu_percent")
        system_memory = values("system_memory_percent")
        gpu_util = values("gpu_util_percent")
        gpu_vram = values("gpu_vram_used_mb")
        gpu_total = values("gpu_vram_total_mb")

        return cls(
            sample_count=len(samples),
            process_cpu_mean_pct=mean_or_none(process_cpu),
            process_cpu_p95_pct=(
                round(percentile(process_cpu, 95.0), 3) if process_cpu else None
            ),
            process_cpu_peak_pct=peak_or_none(process_cpu),
            process_rss_mean_mb=mean_or_none(process_rss),
            process_rss_peak_mb=peak_or_none(process_rss),
            system_cpu_mean_pct=mean_or_none(system_cpu),
            system_cpu_peak_pct=peak_or_none(system_cpu),
            system_memory_mean_pct=mean_or_none(system_memory),
            system_memory_peak_pct=peak_or_none(system_memory),
            gpu_util_mean_pct=mean_or_none(gpu_util),
            gpu_util_peak_pct=peak_or_none(gpu_util),
            gpu_vram_mean_mb=mean_or_none(gpu_vram),
            gpu_vram_peak_mb=peak_or_none(gpu_vram),
            gpu_vram_total_mb=peak_or_none(gpu_total),
        )

    def to_metrics(self) -> dict[str, float | int]:
        metrics: dict[str, float | int] = {"resource.sample_count": self.sample_count}
        for field_name in (
            "process_cpu_mean_pct",
            "process_cpu_p95_pct",
            "process_cpu_peak_pct",
            "process_rss_mean_mb",
            "process_rss_peak_mb",
            "system_cpu_mean_pct",
            "system_cpu_peak_pct",
            "system_memory_mean_pct",
            "system_memory_peak_pct",
            "gpu_util_mean_pct",
            "gpu_util_peak_pct",
            "gpu_vram_mean_mb",
            "gpu_vram_peak_mb",
            "gpu_vram_total_mb",
        ):
            value = getattr(self, field_name)
            if value is not None:
                metrics[f"resource.{field_name}"] = value
        return metrics


class SystemResourceSampler:
    """Collect process/system metrics with optional NVIDIA GPU telemetry."""

    def __init__(self, *, pid: int | None = None) -> None:
        self.pid = int(pid or os.getpid())
        self._psutil = self._load_psutil()
        self._process = None
        if self._psutil is not None:
            self._process = self._psutil.Process(self.pid)
            # Prime counters so later cpu_percent() calls are meaningful.
            self._process.cpu_percent(interval=None)
            self._psutil.cpu_percent(interval=None)
        self._nvidia_smi = shutil.which("nvidia-smi")

    @staticmethod
    def _load_psutil():
        try:
            import psutil  # type: ignore
        except ImportError:
            return None
        return psutil

    def sample(self, *, include_gpu: bool = True) -> ResourceSample:
        process_cpu: float | None = None
        process_rss: float | None = None
        system_cpu: float | None = None
        system_memory: float | None = None

        if self._psutil is not None and self._process is not None:
            try:
                raw_process_cpu = float(self._process.cpu_percent(interval=None))
                logical_cpus = max(1, int(self._psutil.cpu_count() or 1))
                process_cpu = min(100.0, raw_process_cpu / logical_cpus)
                process_rss = float(self._process.memory_info().rss) / (1024.0**2)
                system_cpu = float(self._psutil.cpu_percent(interval=None))
                system_memory = float(self._psutil.virtual_memory().percent)
            except (self._psutil.Error, OSError):
                pass

        gpu_util: float | None = None
        gpu_used: float | None = None
        gpu_total: float | None = None
        if include_gpu and self._nvidia_smi:
            gpu = self._sample_nvidia_gpu()
            if gpu is not None:
                gpu_util, gpu_used, gpu_total = gpu

        return ResourceSample(
            timestamp=time.perf_counter(),
            process_cpu_percent=process_cpu,
            process_rss_mb=process_rss,
            system_cpu_percent=system_cpu,
            system_memory_percent=system_memory,
            gpu_util_percent=gpu_util,
            gpu_vram_used_mb=gpu_used,
            gpu_vram_total_mb=gpu_total,
        )

    def _sample_nvidia_gpu(self) -> tuple[float, float, float] | None:
        assert self._nvidia_smi is not None
        command = [
            self._nvidia_smi,
            "--query-gpu=utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        return _parse_nvidia_smi(completed.stdout)


def _parse_nvidia_smi(output: str) -> tuple[float, float, float] | None:
    """Parse NVIDIA CSV and select the GPU with the highest used VRAM."""

    rows: list[tuple[float, float, float]] = []
    for raw_line in output.splitlines():
        parts = [part.strip() for part in raw_line.split(",")]
        if len(parts) != 3:
            continue
        try:
            utilization, used, total = (float(part) for part in parts)
            rows.append((utilization, used, total))
        except ValueError:
            continue
    if not rows:
        return None
    return max(rows, key=lambda row: row[1])


class SystemResourceMonitor:
    """Background sampler designed to add minimal overhead to benchmark cases."""

    def __init__(
        self,
        *,
        sampler: ResourceSampler | None = None,
        sample_interval_ms: int = 100,
        gpu_interval_ms: int = 1000,
    ) -> None:
        if sample_interval_ms < 20:
            raise ValueError("sample_interval_ms must be at least 20")
        if gpu_interval_ms < sample_interval_ms:
            raise ValueError("gpu_interval_ms cannot be lower than sample interval")
        self.sampler = sampler or SystemResourceSampler()
        self.sample_interval = sample_interval_ms / 1000.0
        self.gpu_interval = gpu_interval_ms / 1000.0
        self.samples: list[ResourceSample] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_gpu_sample = float("-inf")

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("resource monitor already started")
        self._stop_event.clear()
        self._record_sample(force_gpu=True)
        self._thread = threading.Thread(
            target=self._run,
            name="atlas-benchmark-resource-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> ResourceSummary:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(1.0, self.sample_interval * 4))
        self._record_sample(force_gpu=False)
        return ResourceSummary.from_samples(self.samples)

    def _run(self) -> None:
        while not self._stop_event.wait(self.sample_interval):
            self._record_sample(force_gpu=False)

    def _record_sample(self, *, force_gpu: bool) -> None:
        now = time.perf_counter()
        include_gpu = force_gpu or (now - self._last_gpu_sample >= self.gpu_interval)
        sample = self.sampler.sample(include_gpu=include_gpu)
        self.samples.append(sample)
        if include_gpu:
            self._last_gpu_sample = now
