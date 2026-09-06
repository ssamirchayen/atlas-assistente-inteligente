from __future__ import annotations

from atlas.benchmark.resource_monitor import (
    ResourceSample,
    ResourceSummary,
    _parse_nvidia_smi,
)


def test_resource_summary_aggregates_available_metrics():
    summary = ResourceSummary.from_samples(
        [
            ResourceSample(
                timestamp=1.0,
                process_cpu_percent=10,
                process_rss_mb=100,
                system_cpu_percent=20,
                system_memory_percent=40,
                gpu_util_percent=30,
                gpu_vram_used_mb=2000,
                gpu_vram_total_mb=8192,
            ),
            ResourceSample(
                timestamp=2.0,
                process_cpu_percent=30,
                process_rss_mb=140,
                system_cpu_percent=50,
                system_memory_percent=44,
                gpu_util_percent=70,
                gpu_vram_used_mb=2500,
                gpu_vram_total_mb=8192,
            ),
        ]
    )

    metrics = summary.to_metrics()
    assert metrics["resource.sample_count"] == 2
    assert metrics["resource.process_cpu_mean_pct"] == 20.0
    assert metrics["resource.process_rss_peak_mb"] == 140.0
    assert metrics["resource.gpu_util_peak_pct"] == 70.0
    assert metrics["resource.gpu_vram_peak_mb"] == 2500.0


def test_resource_summary_ignores_missing_optional_metrics():
    summary = ResourceSummary.from_samples(
        [ResourceSample(timestamp=1.0, process_rss_mb=64.0)]
    )

    metrics = summary.to_metrics()
    assert metrics["resource.process_rss_peak_mb"] == 64.0
    assert "resource.gpu_vram_peak_mb" not in metrics


def test_parse_nvidia_smi_chooses_gpu_with_highest_vram_use():
    parsed = _parse_nvidia_smi("12, 1000, 8192\n80, 6500, 12288\n")

    assert parsed == (80.0, 6500.0, 12288.0)
