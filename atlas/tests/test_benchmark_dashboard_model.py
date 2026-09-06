from pathlib import Path

from atlas.benchmark.dashboard_model import (
    build_portfolio_payload,
    recent_run_cards,
    run_card,
    suite_cards,
)
from atlas.benchmark.runtime import BenchmarkRuntimeOptions, execute_suite


ROOT = Path(__file__).resolve().parents[2]


def test_suite_cards_expose_current_benchmark_catalog():
    cards = suite_cards(ROOT)
    ids = {card.suite_id for card in cards}
    assert "foundation" in ids
    assert "school_leads" in ids
    assert "helpdesk_provisioning" in ids
    assert "retail_office" in ids
    assert "roi_productivity" in ids
    assert all(card.case_count > 0 for card in cards)


def test_portfolio_payload_keeps_provenance_separated():
    payload = build_portfolio_payload(ROOT, max_measured_runs=2)
    assert payload["frontend"]["ready"] is True
    assert payload["portfolio"]["lab_count"] == 4
    assert len(payload["labs"]) == 4
    assert payload["evidence"]["measured"]["used_in_roi"] is False
    assert payload["evidence"]["simulated"]["used_in_roi"] is True
    assert payload["evidence"]["economic_projection"]["used_in_roi"] is True
    assert payload["disclaimer"]


def test_runtime_executes_foundation_for_frontend_contract():
    run, saved = execute_suite(
        ROOT,
        "foundation",
        version="test-dashboard",
        options=BenchmarkRuntimeOptions(
            resource_monitoring=False,
            save_run=False,
        ),
    )
    assert saved is None
    assert run.summary.failed == 0
    assert run.summary.errors == 0
    assert run.summary.passed == 3

    card = run_card(run)
    assert card.suite_id == "foundation"
    assert card.weighted_score == 100.0
    assert card.live is False


def test_recent_run_cards_handles_missing_history(tmp_path):
    assert recent_run_cards(tmp_path) == ()
