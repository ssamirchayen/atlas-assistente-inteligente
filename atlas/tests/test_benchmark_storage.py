from __future__ import annotations

from atlas.benchmark.models import (
    BenchmarkCase,
    BenchmarkKind,
    BenchmarkSuite,
)
from atlas.benchmark.runner import BenchmarkRunner
from atlas.benchmark.storage import BenchmarkRunStore


def test_store_round_trip(tmp_path):
    case = BenchmarkCase(
        case_id="foundation.ok",
        title="OK",
        domain="benchmark",
        executor="test.ok",
    )
    suite = BenchmarkSuite(
        suite_id="foundation",
        title="Foundation",
        kind=BenchmarkKind.TECHNICAL,
        cases=(case,),
    )
    runner = BenchmarkRunner(tmp_path)
    runner.register_executor("test.ok", lambda _case, _context: True)
    run = runner.run_suite(suite, atlas_version="1.0.0", seed=27)

    store = BenchmarkRunStore(tmp_path / "runs")
    path = store.save(run)
    restored = store.load(run.run_id)

    assert path.exists()
    assert restored.run_id == run.run_id
    assert restored.summary == run.summary
    assert restored.results[0].case_id == "foundation.ok"
