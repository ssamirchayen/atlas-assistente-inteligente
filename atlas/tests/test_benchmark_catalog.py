from __future__ import annotations

import json

import pytest

from atlas.benchmark.catalog import BenchmarkCatalog
from atlas.benchmark.models import BenchmarkKind


def test_catalog_loads_suite(tmp_path):
    suites = tmp_path / "suites"
    suites.mkdir()
    (suites / "school.json").write_text(
        json.dumps(
            {
                "id": "school",
                "title": "School Lab",
                "kind": "business_simulation",
                "cases": [
                    {
                        "id": "school.lead",
                        "title": "Lead",
                        "domain": "school",
                        "executor": "school.lead",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    suite = BenchmarkCatalog(suites).get("school")

    assert suite.kind is BenchmarkKind.BUSINESS_SIMULATION
    assert suite.cases[0].case_id == "school.lead"


def test_catalog_rejects_duplicate_suite_ids(tmp_path):
    suites = tmp_path / "suites"
    suites.mkdir()
    payload = {
        "id": "same",
        "title": "Same",
        "kind": "technical",
        "cases": [
            {
                "id": "same.case",
                "title": "Case",
                "domain": "core",
                "executor": "benchmark.noop",
            }
        ],
    }
    for name in ("a.json", "b.json"):
        (suites / name).write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate benchmark suite"):
        BenchmarkCatalog(suites).load()
