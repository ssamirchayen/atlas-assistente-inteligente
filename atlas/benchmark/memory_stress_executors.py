"""Memory and stress benchmark executors for Sprint 27 stage 6.

All database work is isolated inside the benchmark scratch directory. The
executors intentionally disable semantic embeddings so this suite measures the
local SQLite memory layer without depending on Ollama or external services.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import fmean

from .metrics import percentile
from .models import BenchmarkCase, BenchmarkStatus, CaseOutcome
from .runner import BenchmarkContext, BenchmarkRunner


def register_memory_stress_executors(runner: BenchmarkRunner) -> None:
    """Register memory correctness, persistence and stress executors."""

    runner.register_executor("memory.crud_contract", _memory_crud_contract)
    runner.register_executor("memory.persistence", _memory_persistence)
    runner.register_executor("memory.keyed_upsert", _memory_keyed_upsert)
    runner.register_executor("memory.search_accuracy", _memory_search_accuracy)
    runner.register_executor("memory.concurrent_writes", _memory_concurrent_writes)
    runner.register_executor("stress.write_scaling", _stress_write_scaling)
    runner.register_executor("stress.search_scaling", _stress_search_scaling)
    runner.register_executor("stress.reopen_cycles", _stress_reopen_cycles)


def _memory_store(path: Path):
    from atlas.memory.database import MemoryStore

    return MemoryStore(path, semantic_enabled=False)


def _elapsed_ms(started: float) -> float:
    return max(0.0, (time.perf_counter() - started) * 1000.0)


def _latency_metrics(
    prefix: str,
    values: list[float],
) -> dict[str, float | int]:
    if not values:
        return {
            f"{prefix}.count": 0,
            f"{prefix}.mean_ms": 0.0,
            f"{prefix}.p95_ms": 0.0,
            f"{prefix}.max_ms": 0.0,
        }
    return {
        f"{prefix}.count": len(values),
        f"{prefix}.mean_ms": round(fmean(values), 3),
        f"{prefix}.p95_ms": round(percentile(values, 95.0), 3),
        f"{prefix}.max_ms": round(max(values), 3),
    }


def _degradation_pct(baseline: float, current: float) -> float:
    if baseline <= 0:
        return 0.0
    return round(((current / baseline) - 1.0) * 100.0, 3)


def _memory_crud_contract(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    database_path = context.scratch_dir / "memory-crud.db"

    with _memory_store(database_path) as memory:
        created = memory.remember_record(
            "Atlas benchmark memory original",
            category="benchmark",
            source="synthetic",
            importance=0.8,
        )
        fetched = memory.get(created.id)
        updated = memory.update(
            created.id,
            content="Atlas benchmark memory updated",
            importance=0.9,
        )
        forgotten = memory.forget(created.id)
        hidden = memory.get(created.id) is None
        inactive = memory.get(created.id, include_inactive=True)
        restored = memory.restore(created.id)
        final_record = memory.get(created.id)

    checks = {
        "create": created.active,
        "read": fetched is not None and fetched.content == created.content,
        "update": (
            updated is not None
            and updated.content == "Atlas benchmark memory updated"
            and updated.importance == 0.9
        ),
        "forget": forgotten and hidden,
        "inactive_visible": inactive is not None and not inactive.active,
        "restore": restored,
        "restored_content": (
            final_record is not None
            and final_record.content == "Atlas benchmark memory updated"
        ),
    }
    passed_count = sum(checks.values())
    total = len(checks)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            **checks,
            "checks_total": total,
            "checks_passed": passed_count,
            "sandbox_only": True,
        },
        details=(
            f"Memory CRUD lifecycle matched {passed_count}/{total} checks.",
        ),
    )


def _memory_persistence(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    record_count = int(case.parameters.get("records", 25))
    if record_count <= 0:
        raise ValueError("records must be positive")

    database_path = context.scratch_dir / "memory-persistence.db"
    target_index = max(0, record_count // 2)
    target_token = f"persisttarget{target_index:04d}"

    with _memory_store(database_path) as memory:
        ids = []
        for index in range(record_count):
            record = memory.remember_record(
                f"Persistent benchmark item {index} token persisttarget{index:04d}",
                category="benchmark",
                source="synthetic",
            )
            ids.append(record.id)

    reopen_started = time.perf_counter()
    with _memory_store(database_path) as reopened:
        reopen_ms = _elapsed_ms(reopen_started)
        records = reopened.list_records(limit=record_count + 5)
        target = reopened.search_records(target_token, limit=1)
        first = reopened.get(ids[0])
        last = reopened.get(ids[-1])

    checks = {
        "record_count": len(records) == record_count,
        "target_found": bool(target and target[0].id == ids[target_index]),
        "first_persisted": first is not None,
        "last_persisted": last is not None,
        "database_exists": database_path.is_file(),
    }
    passed_count = sum(checks.values())
    total = len(checks)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            **checks,
            "records": record_count,
            "reopen_ms": round(reopen_ms, 3),
            "database_bytes": database_path.stat().st_size,
            "sandbox_only": True,
        },
        details=(
            "Memory records survived close/reopen and remained searchable.",
        ),
    )


def _memory_keyed_upsert(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    del case
    database_path = context.scratch_dir / "memory-keyed.db"

    with _memory_store(database_path) as memory:
        created, created_state = memory.upsert_keyed_record(
            "Curso de Radiologia",
            memory_key="benchmark.course",
            category="benchmark",
            source="synthetic",
            importance=0.7,
        )
        unchanged, unchanged_state = memory.upsert_keyed_record(
            "Curso de Radiologia",
            memory_key="benchmark.course",
            category="benchmark",
            source="synthetic",
            importance=0.7,
        )
        updated, updated_state = memory.upsert_keyed_record(
            "Curso de Radiologia - turma noturna",
            memory_key="benchmark.course",
            category="benchmark",
            source="synthetic",
            importance=0.8,
        )
        keyed = memory.get_by_key("benchmark.course")
        active_records = memory.list_records(limit=10)

    checks = {
        "created_state": created_state == "created",
        "unchanged_state": unchanged_state == "unchanged",
        "updated_state": updated_state == "updated",
        "stable_id": created.id == unchanged.id == updated.id,
        "single_active_record": len(active_records) == 1,
        "final_value": (
            keyed is not None
            and keyed.content == "Curso de Radiologia - turma noturna"
            and keyed.importance == 0.8
        ),
    }
    passed_count = sum(checks.values())
    total = len(checks)
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            **checks,
            "checks_total": total,
            "checks_passed": passed_count,
            "sandbox_only": True,
        },
        details=(
            f"Keyed memory upsert matched {passed_count}/{total} checks.",
        ),
    )


def _memory_search_accuracy(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    targets = int(case.parameters.get("targets", 12))
    decoys = int(case.parameters.get("decoys", 24))
    if targets <= 0 or decoys < 0:
        raise ValueError("targets must be positive and decoys cannot be negative")

    database_path = context.scratch_dir / "memory-search.db"
    latencies: list[float] = []
    hits = 0

    with _memory_store(database_path) as memory:
        for index in range(decoys):
            memory.remember_record(
                f"Synthetic decoy record {index} generic benchmark content",
                category="benchmark",
                source="synthetic",
            )

        expected_ids: dict[str, int] = {}
        for index in range(targets):
            token = f"searchtarget{index:04d}"
            record = memory.remember_record(
                f"Synthetic target {index} unique token {token}",
                category="benchmark",
                source="synthetic",
            )
            expected_ids[token] = record.id

        for token, expected_id in expected_ids.items():
            started = time.perf_counter()
            matches = memory.search_records(token, limit=1)
            latencies.append(_elapsed_ms(started))
            if matches and matches[0].id == expected_id:
                hits += 1

    accuracy = round(hits / targets * 100.0, 3)
    passed = hits == targets
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=accuracy,
        metrics={
            "queries": targets,
            "hits": hits,
            "accuracy_pct": accuracy,
            "records_seeded": targets + decoys,
            "sandbox_only": True,
            **_latency_metrics("search", latencies),
        },
        details=(
            f"Lexical memory search returned the expected top result for {hits}/{targets} queries.",
        ),
    )


def _memory_concurrent_writes(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    record_count = int(case.parameters.get("records", 100))
    workers = int(case.parameters.get("workers", 4))
    if record_count <= 0 or workers <= 0:
        raise ValueError("records and workers must be positive")

    database_path = context.scratch_dir / "memory-concurrent.db"
    latencies: list[float] = []

    with _memory_store(database_path) as memory:
        def write_record(index: int) -> tuple[int, float]:
            started = time.perf_counter()
            record = memory.remember_record(
                f"Concurrent benchmark record {index}",
                category="benchmark",
                source="synthetic",
                memory_key=f"benchmark.concurrent.{index}",
            )
            return record.id, _elapsed_ms(started)

        run_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(write_record, range(record_count)))
        total_ms = _elapsed_ms(run_started)

        ids = [item[0] for item in results]
        latencies.extend(item[1] for item in results)
        records = memory.list_records(limit=record_count + 5)
        integrity_row = memory.conn.execute("PRAGMA integrity_check").fetchone()

    integrity_ok = bool(integrity_row and str(integrity_row[0]).lower() == "ok")
    checks = {
        "record_count": len(records) == record_count,
        "unique_ids": len(set(ids)) == record_count,
        "sqlite_integrity": integrity_ok,
    }
    passed_count = sum(checks.values())
    total = len(checks)
    throughput = record_count / (total_ms / 1000.0) if total_ms > 0 else 0.0
    score = round(passed_count / total * 100.0, 3)
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed_count == total else BenchmarkStatus.FAIL,
        score=score,
        metrics={
            **checks,
            "records": record_count,
            "workers": workers,
            "total_ms": round(total_ms, 3),
            "writes_per_second": round(throughput, 3),
            "sandbox_only": True,
            **_latency_metrics("write", latencies),
        },
        details=(
            f"Concurrent memory writes completed {record_count} records with {workers} workers.",
        ),
    )


def _stress_write_scaling(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    raw_sizes = case.parameters.get("batch_sizes", [10, 50, 100, 500])
    if not isinstance(raw_sizes, list) or not raw_sizes:
        raise ValueError("batch_sizes must be a non-empty list")
    batch_sizes = [int(value) for value in raw_sizes]
    if any(value <= 0 for value in batch_sizes):
        raise ValueError("batch_sizes must contain only positive integers")

    database_path = context.scratch_dir / "stress-write.db"
    metrics: dict[str, float | int | str | bool] = {
        "sandbox_only": True,
        "batches": len(batch_sizes),
    }
    batch_means: list[float] = []
    expected_total = sum(batch_sizes)
    next_index = 0

    with _memory_store(database_path) as memory:
        for batch_size in batch_sizes:
            latencies: list[float] = []
            batch_started = time.perf_counter()
            for _ in range(batch_size):
                index = next_index
                next_index += 1
                started = time.perf_counter()
                memory.remember_record(
                    f"Stress write record {index}",
                    category="benchmark",
                    source="synthetic",
                )
                latencies.append(_elapsed_ms(started))
            batch_ms = _elapsed_ms(batch_started)
            mean_ms = fmean(latencies) if latencies else 0.0
            batch_means.append(mean_ms)
            throughput = (
                batch_size / (batch_ms / 1000.0)
                if batch_ms > 0
                else 0.0
            )
            prefix = f"batch_{batch_size}"
            metrics[f"{prefix}.duration_ms"] = round(batch_ms, 3)
            metrics[f"{prefix}.mean_write_ms"] = round(mean_ms, 3)
            metrics[f"{prefix}.p95_write_ms"] = round(
                percentile(latencies, 95.0),
                3,
            )
            metrics[f"{prefix}.writes_per_second"] = round(throughput, 3)

        records = memory.list_records(limit=expected_total + 5)
        integrity_row = memory.conn.execute("PRAGMA integrity_check").fetchone()

    integrity_ok = bool(integrity_row and str(integrity_row[0]).lower() == "ok")
    final_mean = batch_means[-1]
    baseline_mean = batch_means[0]
    metrics["records_expected"] = expected_total
    metrics["records_persisted"] = len(records)
    metrics["sqlite_integrity"] = integrity_ok
    metrics["mean_write_degradation_pct"] = _degradation_pct(
        baseline_mean,
        final_mean,
    )
    metrics["database_bytes"] = database_path.stat().st_size

    passed = len(records) == expected_total and integrity_ok
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=100.0 if passed else 0.0,
        metrics=metrics,
        details=(
            "Write scaling completed; degradation is reported as a metric and does not alter functional score.",
        ),
    )


def _stress_search_scaling(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    raw_sizes = case.parameters.get("dataset_sizes", [10, 100, 500])
    query_count = int(case.parameters.get("queries_per_size", 20))
    if not isinstance(raw_sizes, list) or not raw_sizes:
        raise ValueError("dataset_sizes must be a non-empty list")
    dataset_sizes = [int(value) for value in raw_sizes]
    if any(value <= 0 for value in dataset_sizes) or query_count <= 0:
        raise ValueError("dataset sizes and query count must be positive")
    if dataset_sizes != sorted(set(dataset_sizes)):
        raise ValueError("dataset_sizes must be unique and sorted")

    metrics: dict[str, float | int | str | bool] = {
        "sandbox_only": True,
        "datasets": len(dataset_sizes),
        "queries_per_size": query_count,
    }
    means: list[float] = []
    total_hits = 0
    total_queries = 0

    for dataset_size in dataset_sizes:
        database_path = context.scratch_dir / f"stress-search-{dataset_size}.db"
        latencies: list[float] = []
        hits = 0

        with _memory_store(database_path) as memory:
            ids: list[int] = []
            for index in range(dataset_size):
                token = f"scale{dataset_size}item{index:05d}"
                record = memory.remember_record(
                    f"Search scaling item {index} unique token {token}",
                    category="benchmark",
                    source="synthetic",
                )
                ids.append(record.id)

            sample_count = min(query_count, dataset_size)
            if sample_count == 1:
                indexes = [0]
            else:
                indexes = [
                    round(position * (dataset_size - 1) / (sample_count - 1))
                    for position in range(sample_count)
                ]

            for index in indexes:
                token = f"scale{dataset_size}item{index:05d}"
                started = time.perf_counter()
                matches = memory.search_records(token, limit=1)
                latencies.append(_elapsed_ms(started))
                if matches and matches[0].id == ids[index]:
                    hits += 1

        mean_ms = fmean(latencies) if latencies else 0.0
        means.append(mean_ms)
        total_hits += hits
        total_queries += len(latencies)
        prefix = f"dataset_{dataset_size}"
        metrics[f"{prefix}.queries"] = len(latencies)
        metrics[f"{prefix}.hits"] = hits
        metrics[f"{prefix}.accuracy_pct"] = round(
            hits / len(latencies) * 100.0 if latencies else 0.0,
            3,
        )
        metrics[f"{prefix}.mean_search_ms"] = round(mean_ms, 3)
        metrics[f"{prefix}.p95_search_ms"] = round(
            percentile(latencies, 95.0),
            3,
        )

    accuracy = (
        total_hits / total_queries * 100.0
        if total_queries
        else 0.0
    )
    metrics["accuracy_pct"] = round(accuracy, 3)
    metrics["mean_search_degradation_pct"] = _degradation_pct(
        means[0],
        means[-1],
    )

    passed = total_queries > 0 and total_hits == total_queries
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=round(accuracy, 3),
        metrics=metrics,
        details=(
            "Search scaling measured exact-token retrieval as dataset size increased.",
        ),
    )


def _stress_reopen_cycles(
    case: BenchmarkCase,
    context: BenchmarkContext,
) -> CaseOutcome:
    records_to_seed = int(case.parameters.get("records", 100))
    cycles = int(case.parameters.get("cycles", 5))
    if records_to_seed <= 0 or cycles <= 0:
        raise ValueError("records and cycles must be positive")

    database_path = context.scratch_dir / "stress-reopen.db"
    with _memory_store(database_path) as memory:
        expected_ids = []
        for index in range(records_to_seed):
            record = memory.remember_record(
                f"Reopen cycle benchmark record {index}",
                category="benchmark",
                source="synthetic",
            )
            expected_ids.append(record.id)

    reopen_latencies: list[float] = []
    successful_cycles = 0
    for _ in range(cycles):
        started = time.perf_counter()
        with _memory_store(database_path) as reopened:
            first = reopened.get(expected_ids[0])
            last = reopened.get(expected_ids[-1])
            count = len(reopened.list_records(limit=records_to_seed + 5))
        reopen_latencies.append(_elapsed_ms(started))
        if first is not None and last is not None and count == records_to_seed:
            successful_cycles += 1

    integrity_ok = False
    with _memory_store(database_path) as final_store:
        row = final_store.conn.execute("PRAGMA integrity_check").fetchone()
        integrity_ok = bool(row and str(row[0]).lower() == "ok")

    passed = successful_cycles == cycles and integrity_ok
    return CaseOutcome(
        status=BenchmarkStatus.PASS if passed else BenchmarkStatus.FAIL,
        score=(
            round(successful_cycles / cycles * 100.0, 3)
            if cycles
            else 0.0
        ),
        metrics={
            "records": records_to_seed,
            "cycles": cycles,
            "successful_cycles": successful_cycles,
            "sqlite_integrity": integrity_ok,
            "sandbox_only": True,
            **_latency_metrics("reopen", reopen_latencies),
        },
        details=(
            f"Memory database survived {successful_cycles}/{cycles} reopen cycles.",
        ),
    )
