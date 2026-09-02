import pytest

from atlas.validation.models import (
    BenchmarkPolicy,
    ScenarioDefinition,
    ScenarioStatus,
)


def test_scenario_definition_from_dict() -> None:
    scenario = ScenarioDefinition.from_dict(
        {
            "id": "CORE-TEST",
            "title": "Core test",
            "domain": "Core",
            "execution": "automated",
            "tags": ["smoke"],
        }
    )

    assert scenario.scenario_id == "CORE-TEST"
    assert scenario.domain == "core"
    assert scenario.execution == "automated"
    assert scenario.tags == ("smoke",)
    assert ScenarioStatus.PASS.value == "PASS"


def test_scenario_definition_rejects_invalid_execution() -> None:
    try:
        ScenarioDefinition.from_dict(
            {
                "id": "BAD-001",
                "title": "Bad",
                "domain": "core",
                "execution": "unsafe",
            }
        )
    except ValueError as exc:
        assert "Unsupported execution mode" in str(exc)
    else:
        raise AssertionError("invalid execution mode should fail")


def test_automated_scenario_loads_benchmark_policy() -> None:
    scenario = ScenarioDefinition.from_dict(
        {
            "id": "PERF-TEST",
            "title": "Performance",
            "domain": "performance",
            "execution": "automated",
            "benchmark": {
                "iterations": 20,
                "warmup_iterations": 2,
                "p95_ms_max": 50,
                "memory_delta_mb_max": 16,
            },
        }
    )

    assert scenario.benchmark == BenchmarkPolicy(
        iterations=20,
        warmup_iterations=2,
        p95_ms_max=50,
        memory_delta_mb_max=16,
    )


@pytest.mark.parametrize("iterations", [0, 2, 101])
def test_benchmark_policy_rejects_unsafe_iteration_count(iterations) -> None:
    with pytest.raises(ValueError, match="iterations"):
        BenchmarkPolicy(iterations=iterations)


def test_manual_scenario_cannot_declare_benchmark() -> None:
    with pytest.raises(ValueError, match="only for automated"):
        ScenarioDefinition.from_dict(
            {
                "id": "MANUAL-PERF",
                "title": "Manual",
                "domain": "performance",
                "execution": "manual",
                "benchmark": {"iterations": 10},
            }
        )
