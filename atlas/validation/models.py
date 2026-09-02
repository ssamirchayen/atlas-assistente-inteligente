"""Data models used by the Atlas Validation Lab."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ScenarioStatus(StrEnum):
    """Execution status for a validation scenario."""

    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL = "MANUAL"
    PLANNED = "PLANNED"
    SKIP = "SKIP"


@dataclass(frozen=True, slots=True)
class BenchmarkPolicy:
    """Safe repetition and resource budgets for an automated scenario."""

    iterations: int = 10
    warmup_iterations: int = 1
    p50_ms_max: float | None = None
    p95_ms_max: float | None = None
    cpu_percent_max: float | None = None
    memory_delta_mb_max: float | None = None

    def __post_init__(self) -> None:
        if not 3 <= self.iterations <= 100:
            raise ValueError("Benchmark iterations must be between 3 and 100")
        if not 0 <= self.warmup_iterations <= 10:
            raise ValueError("Benchmark warmup_iterations must be between 0 and 10")

        for name in (
            "p50_ms_max",
            "p95_ms_max",
            "cpu_percent_max",
            "memory_delta_mb_max",
        ):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"Benchmark {name} must be positive")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkPolicy":
        return cls(
            iterations=int(payload.get("iterations", 10)),
            warmup_iterations=int(payload.get("warmup_iterations", 1)),
            p50_ms_max=_optional_float(payload.get("p50_ms_max")),
            p95_ms_max=_optional_float(payload.get("p95_ms_max")),
            cpu_percent_max=_optional_float(payload.get("cpu_percent_max")),
            memory_delta_mb_max=_optional_float(
                payload.get("memory_delta_mb_max")
            ),
        )


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    """Declarative definition of one Atlas validation scenario."""

    scenario_id: str
    title: str
    domain: str
    execution: str
    risk: str = "low"
    phase: str = "current"
    tags: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    expected: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: tuple[dict[str, Any], ...] = ()
    benchmark: BenchmarkPolicy | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScenarioDefinition":
        required = ("id", "title", "domain", "execution")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Scenario missing required field(s): {joined}")

        execution = str(payload["execution"]).lower()
        if execution not in {"automated", "manual", "planned"}:
            raise ValueError(f"Unsupported execution mode: {execution}")

        benchmark_payload = payload.get("benchmark")
        if benchmark_payload is not None and not isinstance(
            benchmark_payload, dict
        ):
            raise ValueError("Scenario benchmark must be an object")
        if benchmark_payload is not None and execution != "automated":
            raise ValueError("Benchmark is supported only for automated scenarios")

        return cls(
            scenario_id=str(payload["id"]),
            title=str(payload["title"]),
            domain=str(payload["domain"]).lower(),
            execution=execution,
            risk=str(payload.get("risk", "low")).lower(),
            phase=str(payload.get("phase", "current")).lower(),
            tags=tuple(str(item) for item in payload.get("tags", [])),
            preconditions=tuple(
                str(item) for item in payload.get("preconditions", [])
            ),
            steps=tuple(str(item) for item in payload.get("steps", [])),
            expected=tuple(str(item) for item in payload.get("expected", [])),
            metrics=dict(payload.get("metrics", {})),
            checks=tuple(dict(item) for item in payload.get("checks", [])),
            benchmark=(
                BenchmarkPolicy.from_dict(benchmark_payload)
                if benchmark_payload is not None
                else None
            ),
        )


@dataclass(slots=True)
class ScenarioResult:
    """Result produced after evaluating one scenario."""

    scenario_id: str
    title: str
    domain: str
    status: ScenarioStatus
    duration_ms: float = 0.0
    details: list[str] = field(default_factory=list)
    metrics: dict[str, float | int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is ScenarioStatus.PASS
