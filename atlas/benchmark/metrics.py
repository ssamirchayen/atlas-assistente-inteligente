"""Metric helpers for Atlas Benchmark & Validation Lab."""

from __future__ import annotations

from statistics import fmean
from typing import Iterable


def percentile(values: Iterable[float], q: float) -> float:
    """Return a linearly interpolated percentile for numeric values."""

    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= q <= 100.0:
        raise ValueError("percentile q must be between 0 and 100")
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * (q / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize_latency_ms(values: Iterable[float]) -> dict[str, float | int]:
    """Build stable latency statistics used by console and JSON reports."""

    samples = [max(0.0, float(value)) for value in values]
    if not samples:
        return {"latency_count": 0}

    return {
        "latency_count": len(samples),
        "latency_min_ms": round(min(samples), 3),
        "latency_mean_ms": round(fmean(samples), 3),
        "latency_p50_ms": round(percentile(samples, 50.0), 3),
        "latency_p95_ms": round(percentile(samples, 95.0), 3),
        "latency_p99_ms": round(percentile(samples, 99.0), 3),
        "latency_max_ms": round(max(samples), 3),
    }
