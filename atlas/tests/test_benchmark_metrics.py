from __future__ import annotations

import pytest

from atlas.benchmark.metrics import percentile, summarize_latency_ms


def test_percentile_uses_linear_interpolation():
    assert percentile([0, 10, 20, 30], 50) == pytest.approx(15.0)
    assert percentile([0, 10, 20, 30], 95) == pytest.approx(28.5)


def test_percentile_rejects_empty_values():
    with pytest.raises(ValueError, match="at least one"):
        percentile([], 50)


def test_latency_summary_contains_expected_percentiles():
    summary = summarize_latency_ms([10, 20, 30, 40])

    assert summary["latency_count"] == 4
    assert summary["latency_mean_ms"] == 25.0
    assert summary["latency_p50_ms"] == 25.0
    assert summary["latency_p95_ms"] == pytest.approx(38.5)
    assert summary["latency_max_ms"] == 40.0
