from __future__ import annotations

import pytest

from atlas.benchmark.models import (
    BenchmarkCase,
    BenchmarkKind,
    BenchmarkStatus,
    BenchmarkSuite,
    BenchmarkSummary,
    CaseResult,
)


def test_case_from_dict_inherits_suite_kind():
    case = BenchmarkCase.from_dict(
        {
            "id": "school.lead",
            "title": "School lead",
            "domain": "school",
            "executor": "school.simulate",
        },
        default_kind=BenchmarkKind.BUSINESS_SIMULATION,
    )

    assert case.kind is BenchmarkKind.BUSINESS_SIMULATION


def test_case_rejects_invalid_weight():
    with pytest.raises(ValueError, match="weight"):
        BenchmarkCase(
            case_id="core.latency",
            title="Latency",
            domain="core",
            executor="core.latency",
            weight=0,
        )


def test_suite_rejects_duplicate_case_ids():
    case = BenchmarkCase(
        case_id="foundation.same",
        title="Same",
        domain="benchmark",
        executor="benchmark.noop",
    )

    with pytest.raises(ValueError, match="Duplicate"):
        BenchmarkSuite(
            suite_id="foundation",
            title="Foundation",
            kind=BenchmarkKind.TECHNICAL,
            cases=(case, case),
        )


def test_summary_uses_weighted_score_and_excludes_skips():
    results = (
        CaseResult(
            case_id="a",
            title="A",
            domain="core",
            kind=BenchmarkKind.TECHNICAL,
            status=BenchmarkStatus.PASS,
            score=100,
            weight=3,
            duration_ms=1,
        ),
        CaseResult(
            case_id="b",
            title="B",
            domain="core",
            kind=BenchmarkKind.TECHNICAL,
            status=BenchmarkStatus.FAIL,
            score=0,
            weight=1,
            duration_ms=1,
        ),
        CaseResult(
            case_id="c",
            title="C",
            domain="core",
            kind=BenchmarkKind.TECHNICAL,
            status=BenchmarkStatus.SKIP,
            score=0,
            weight=100,
            duration_ms=0,
        ),
    )

    summary = BenchmarkSummary.from_results(results)

    assert summary.success_rate == 50.0
    assert summary.weighted_score == 75.0
    assert summary.skipped == 1
