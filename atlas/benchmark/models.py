"""Core data models for Atlas Benchmark.

The models are intentionally generic so the same engine can execute technical
checks and synthetic business simulations without coupling them to the Atlas
GUI, voice stack or operational kernel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BenchmarkKind(StrEnum):
    """Top-level benchmark families."""

    TECHNICAL = "technical"
    BUSINESS_SIMULATION = "business_simulation"


class BenchmarkStatus(StrEnum):
    """Execution result for one benchmark case."""

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One deterministic unit of benchmark work."""

    case_id: str
    title: str
    domain: str
    executor: str
    kind: BenchmarkKind = BenchmarkKind.TECHNICAL
    weight: float = 1.0
    tags: tuple[str, ...] = ()
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        for field_name in ("case_id", "title", "domain", "executor"):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{field_name} cannot be empty")
        if any(char.isspace() for char in self.case_id):
            raise ValueError("case_id cannot contain whitespace")
        if self.weight <= 0:
            raise ValueError("weight must be positive")

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        default_kind: BenchmarkKind = BenchmarkKind.TECHNICAL,
    ) -> "BenchmarkCase":
        required = ("id", "title", "domain", "executor")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError(
                "Benchmark case missing required field(s): " + ", ".join(missing)
            )

        raw_kind = payload.get("kind", default_kind.value)
        try:
            kind = BenchmarkKind(str(raw_kind).lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported benchmark kind: {raw_kind}") from exc

        return cls(
            case_id=str(payload["id"]).strip(),
            title=str(payload["title"]).strip(),
            domain=str(payload["domain"]).strip().lower(),
            executor=str(payload["executor"]).strip(),
            kind=kind,
            weight=float(payload.get("weight", 1.0)),
            tags=tuple(str(item).strip() for item in payload.get("tags", [])),
            parameters=dict(payload.get("parameters", {})),
            enabled=bool(payload.get("enabled", True)),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    """Named set of benchmark cases executed as one run."""

    suite_id: str
    title: str
    kind: BenchmarkKind
    cases: tuple[BenchmarkCase, ...]
    description: str = ""
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.suite_id.strip():
            raise ValueError("suite_id cannot be empty")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.cases:
            raise ValueError("benchmark suite must contain at least one case")

        ids = [case.case_id for case in self.cases]
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        if duplicates:
            raise ValueError(
                "Duplicate benchmark case id(s): " + ", ".join(duplicates)
            )

        mismatched = [
            case.case_id for case in self.cases if case.kind is not self.kind
        ]
        if mismatched:
            raise ValueError(
                "Benchmark case kind differs from suite kind: "
                + ", ".join(mismatched)
            )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkSuite":
        required = ("id", "title", "kind", "cases")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError(
                "Benchmark suite missing required field(s): " + ", ".join(missing)
            )

        try:
            kind = BenchmarkKind(str(payload["kind"]).lower())
        except ValueError as exc:
            raise ValueError(
                f"Unsupported benchmark kind: {payload['kind']}"
            ) from exc

        raw_cases = payload["cases"]
        if not isinstance(raw_cases, list):
            raise ValueError("Benchmark suite cases must be a list")

        cases = tuple(
            BenchmarkCase.from_dict(item, default_kind=kind) for item in raw_cases
        )
        return cls(
            suite_id=str(payload["id"]).strip(),
            title=str(payload["title"]).strip(),
            kind=kind,
            cases=cases,
            description=str(payload.get("description", "")).strip(),
            tags=tuple(str(item).strip() for item in payload.get("tags", [])),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """Executor-owned outcome before timing/run metadata are attached."""

    status: BenchmarkStatus = BenchmarkStatus.PASS
    score: float = 100.0
    metrics: dict[str, float | int | str | bool] = field(default_factory=dict)
    details: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.score) <= 100.0:
            raise ValueError("score must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class CaseResult:
    """Normalized result for one benchmark case."""

    case_id: str
    title: str
    domain: str
    kind: BenchmarkKind
    status: BenchmarkStatus
    score: float
    weight: float
    duration_ms: float
    metrics: dict[str, float | int | str | bool] = field(default_factory=dict)
    details: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    """Aggregate counts and scores for a run."""

    total: int
    evaluated: int
    passed: int
    failed: int
    errors: int
    skipped: int
    success_rate: float
    weighted_score: float

    @classmethod
    def from_results(cls, results: tuple[CaseResult, ...]) -> "BenchmarkSummary":
        passed = sum(result.status is BenchmarkStatus.PASS for result in results)
        failed = sum(result.status is BenchmarkStatus.FAIL for result in results)
        errors = sum(result.status is BenchmarkStatus.ERROR for result in results)
        skipped = sum(result.status is BenchmarkStatus.SKIP for result in results)
        evaluated_results = tuple(
            result
            for result in results
            if result.status is not BenchmarkStatus.SKIP
        )
        evaluated = len(evaluated_results)

        success_rate = (passed / evaluated * 100.0) if evaluated else 0.0
        total_weight = sum(result.weight for result in evaluated_results)
        weighted_score = (
            sum(result.score * result.weight for result in evaluated_results)
            / total_weight
            if total_weight
            else 0.0
        )

        return cls(
            total=len(results),
            evaluated=evaluated,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            success_rate=round(success_rate, 3),
            weighted_score=round(weighted_score, 3),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkRun:
    """Immutable record of one complete benchmark execution."""

    run_id: str
    suite_id: str
    suite_title: str
    kind: BenchmarkKind
    atlas_version: str
    started_at_utc: str
    finished_at_utc: str
    seed: int
    results: tuple[CaseResult, ...]
    summary: BenchmarkSummary
    metadata: dict[str, Any] = field(default_factory=dict)
