"""Persistence for local benchmark run history."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    BenchmarkKind,
    BenchmarkRun,
    BenchmarkStatus,
    BenchmarkSummary,
    CaseResult,
)


def run_to_dict(run: BenchmarkRun) -> dict[str, Any]:
    """Convert a run to a JSON-safe dictionary."""

    payload = asdict(run)
    payload["kind"] = run.kind.value
    payload["results"] = [
        {
            **asdict(result),
            "kind": result.kind.value,
            "status": result.status.value,
        }
        for result in run.results
    ]
    return payload


def run_from_dict(payload: dict[str, Any]) -> BenchmarkRun:
    """Restore a benchmark run previously produced by :func:`run_to_dict`."""

    results = tuple(
        CaseResult(
            case_id=str(item["case_id"]),
            title=str(item["title"]),
            domain=str(item["domain"]),
            kind=BenchmarkKind(str(item["kind"])),
            status=BenchmarkStatus(str(item["status"])),
            score=float(item["score"]),
            weight=float(item["weight"]),
            duration_ms=float(item["duration_ms"]),
            metrics=dict(item.get("metrics", {})),
            details=tuple(str(value) for value in item.get("details", [])),
            error=item.get("error"),
        )
        for item in payload.get("results", [])
    )
    summary_payload = dict(payload["summary"])
    summary = BenchmarkSummary(
        total=int(summary_payload["total"]),
        evaluated=int(summary_payload["evaluated"]),
        passed=int(summary_payload["passed"]),
        failed=int(summary_payload["failed"]),
        errors=int(summary_payload["errors"]),
        skipped=int(summary_payload["skipped"]),
        success_rate=float(summary_payload["success_rate"]),
        weighted_score=float(summary_payload["weighted_score"]),
    )
    return BenchmarkRun(
        run_id=str(payload["run_id"]),
        suite_id=str(payload["suite_id"]),
        suite_title=str(payload["suite_title"]),
        kind=BenchmarkKind(str(payload["kind"])),
        atlas_version=str(payload["atlas_version"]),
        started_at_utc=str(payload["started_at_utc"]),
        finished_at_utc=str(payload["finished_at_utc"]),
        seed=int(payload["seed"]),
        results=results,
        summary=summary,
        metadata=dict(payload.get("metadata", {})),
    )


class BenchmarkRunStore:
    """Write benchmark history under a local, git-ignored directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, run: BenchmarkRun) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / f"{run.run_id}.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(run_to_dict(run), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination

    def load(self, run_id: str) -> BenchmarkRun:
        path = self.root / f"{run_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid benchmark run payload: {path}")
        return run_from_dict(payload)

    def list_run_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(path.stem for path in self.root.glob("*.json"))
