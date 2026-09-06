from __future__ import annotations

from pathlib import Path

from atlas.benchmark.memory_stress_executors import (
    _memory_concurrent_writes,
    _memory_crud_contract,
    _memory_keyed_upsert,
    _memory_persistence,
    _memory_search_accuracy,
    _stress_reopen_cycles,
    _stress_search_scaling,
    _stress_write_scaling,
    register_memory_stress_executors,
)
from atlas.benchmark.models import BenchmarkCase, BenchmarkStatus
from atlas.benchmark.runner import BenchmarkContext, BenchmarkRunner


def _context(tmp_path: Path) -> BenchmarkContext:
    return BenchmarkContext(
        project_root=tmp_path,
        scratch_dir=tmp_path,
        run_id="test-run",
        seed=27,
        case_seed=606,
    )


def _case(executor: str, **parameters) -> BenchmarkCase:
    return BenchmarkCase(
        case_id="memory_stress.test",
        title="Memory stress test",
        domain="memory_stress",
        executor=executor,
        parameters=parameters,
    )


def test_memory_crud_contract_isolated_and_complete(tmp_path):
    outcome = _memory_crud_contract(
        _case("memory.crud_contract"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.score == 100.0
    assert outcome.metrics["sandbox_only"] is True
    assert outcome.metrics["checks_passed"] == outcome.metrics["checks_total"]


def test_memory_persistence_survives_reopen(tmp_path):
    outcome = _memory_persistence(
        _case("memory.persistence", records=12),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["records"] == 12
    assert outcome.metrics["target_found"] is True
    assert outcome.metrics["database_bytes"] > 0


def test_keyed_upsert_keeps_one_active_record(tmp_path):
    outcome = _memory_keyed_upsert(
        _case("memory.keyed_upsert"),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["single_active_record"] is True
    assert outcome.metrics["stable_id"] is True
    assert outcome.metrics["final_value"] is True


def test_memory_search_accuracy_returns_expected_target(tmp_path):
    outcome = _memory_search_accuracy(
        _case("memory.search_accuracy", targets=6, decoys=8),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["accuracy_pct"] == 100.0
    assert outcome.metrics["queries"] == 6
    assert outcome.metrics["search.p95_ms"] >= 0


def test_concurrent_writes_keep_database_integrity(tmp_path):
    outcome = _memory_concurrent_writes(
        _case("memory.concurrent_writes", records=32, workers=4),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["record_count"] is True
    assert outcome.metrics["unique_ids"] is True
    assert outcome.metrics["sqlite_integrity"] is True
    assert outcome.metrics["writes_per_second"] >= 0


def test_write_scaling_records_each_batch(tmp_path):
    outcome = _stress_write_scaling(
        _case("stress.write_scaling", batch_sizes=[3, 5, 10]),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["records_expected"] == 18
    assert outcome.metrics["records_persisted"] == 18
    assert "batch_10.p95_write_ms" in outcome.metrics
    assert "mean_write_degradation_pct" in outcome.metrics


def test_search_scaling_keeps_accuracy_across_dataset_sizes(tmp_path):
    outcome = _stress_search_scaling(
        _case(
            "stress.search_scaling",
            dataset_sizes=[5, 20],
            queries_per_size=5,
        ),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["accuracy_pct"] == 100.0
    assert outcome.metrics["dataset_5.accuracy_pct"] == 100.0
    assert outcome.metrics["dataset_20.accuracy_pct"] == 100.0


def test_reopen_cycles_keep_records_and_integrity(tmp_path):
    outcome = _stress_reopen_cycles(
        _case("stress.reopen_cycles", records=10, cycles=3),
        _context(tmp_path),
    )

    assert outcome.status is BenchmarkStatus.PASS
    assert outcome.metrics["successful_cycles"] == 3
    assert outcome.metrics["sqlite_integrity"] is True
    assert outcome.metrics["reopen.p95_ms"] >= 0


def test_register_memory_stress_executors_registers_suite_contract(tmp_path):
    runner = BenchmarkRunner(tmp_path)
    register_memory_stress_executors(runner)

    expected = {
        "memory.crud_contract",
        "memory.persistence",
        "memory.keyed_upsert",
        "memory.search_accuracy",
        "memory.concurrent_writes",
        "stress.write_scaling",
        "stress.search_scaling",
        "stress.reopen_cycles",
    }
    assert expected.issubset(runner._executors)
