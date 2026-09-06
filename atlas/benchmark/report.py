"""Compact text reporting for Sprint 27 benchmark runs."""

from __future__ import annotations

from .metrics import summarize_latency_ms
from .models import BenchmarkRun


def _format_resource_suffix(metrics: dict[str, object]) -> str:
    parts: list[str] = []
    cpu = metrics.get("resource.process_cpu_mean_pct")
    ram = metrics.get("resource.process_rss_peak_mb")
    gpu = metrics.get("resource.gpu_vram_peak_mb")
    if isinstance(cpu, (int, float)):
        parts.append(f"cpu={float(cpu):.1f}%")
    if isinstance(ram, (int, float)):
        parts.append(f"ram={float(ram):.1f}MB")
    if isinstance(gpu, (int, float)):
        parts.append(f"vram={float(gpu):.0f}MB")
    return (" | " + " ".join(parts)) if parts else ""


def render_console(run: BenchmarkRun) -> str:
    summary = run.summary
    lines = [
        "ATLAS BENCHMARK & VALIDATION LAB",
        "=" * 72,
        f"Run:     {run.run_id}",
        f"Suite:   {run.suite_title} ({run.suite_id})",
        f"Kind:    {run.kind.value}",
        f"Version: {run.atlas_version}",
        "-" * 72,
    ]

    for result in run.results:
        lines.append(
            f"[{result.status.value:5}] {result.case_id:28} "
            f"{result.duration_ms:9.3f} ms  score={result.score:6.2f}"
            f"{_format_resource_suffix(result.metrics)}"
        )
        if result.error:
            lines.append(f"        error: {result.error}")
        if result.status.value == "SKIP" and result.details:
            lines.append(f"        reason: {result.details[0]}")
        monitor_error = result.metrics.get("resource.monitor_error")
        if monitor_error:
            lines.append(f"        resource monitor: {monitor_error}")

    latency = summarize_latency_ms(
        result.duration_ms
        for result in run.results
        if result.status.value != "SKIP"
    )
    lines.extend(
        [
            "-" * 72,
            f"Cases: {summary.total} | Evaluated: {summary.evaluated} | "
            f"Pass: {summary.passed} | Fail: {summary.failed} | "
            f"Error: {summary.errors} | Skip: {summary.skipped}",
            f"Success rate: {summary.success_rate:.2f}%",
            f"Weighted score: {summary.weighted_score:.2f}/100",
        ]
    )
    if latency.get("latency_count"):
        lines.append(
            "Latency: "
            f"mean={latency['latency_mean_ms']:.3f} ms | "
            f"p50={latency['latency_p50_ms']:.3f} ms | "
            f"p95={latency['latency_p95_ms']:.3f} ms | "
            f"max={latency['latency_max_ms']:.3f} ms"
        )
    return "\n".join(lines)
