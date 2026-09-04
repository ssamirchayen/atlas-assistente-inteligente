from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from atlas.core.resource_manager import (
    ResourceManager,
    RuntimeMetrics,
    WorkloadClass,
)
from atlas.core.runtime_profile import HardwareSnapshot, RuntimeProfileSelector
from atlas.planner.actions import Action
from atlas.planner.results import ExecutionResult
from atlas.planner.task_manager import TaskManager
from atlas.workflow.engine import WorkflowEngine
from atlas.workflow.state import WorkflowState
from atlas.workflow.step import WorkflowStep


NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[2]


class FixedProbe:
    def __init__(self, value: RuntimeMetrics) -> None:
        self.value = value

    def capture(self) -> RuntimeMetrics:
        return self.value


class StubExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, actions: list[Action]) -> list[ExecutionResult]:
        self.calls += 1
        return [ExecutionResult.ok(actions[0].type, "Concluído.")]


def resource_manager(*, cpu: float = 10) -> ResourceManager:
    profile = RuntimeProfileSelector().select(
        HardwareSnapshot(
            captured_at=NOW,
            total_memory_gb=16,
            available_memory_gb=8,
            logical_cpus=8,
            physical_cpus=4,
            disk_free_gb=100,
        )
    )
    return ResourceManager(
        profile=profile,
        metrics_probe=FixedProbe(
            RuntimeMetrics(
                captured_at=NOW,
                cpu_percent=cpu,
                memory_percent=40,
                available_memory_gb=8,
                process_rss_mb=300,
            )
        ),  # type: ignore[arg-type]
    )


def workflow(action_type: str = "browser.open") -> WorkflowState:
    return WorkflowState(
        steps=[WorkflowStep(action=Action(type=action_type, parameters={}))]
    )


def test_workflow_holds_and_releases_resource_lease() -> None:
    executor = StubExecutor()
    resources = resource_manager()
    engine = WorkflowEngine(executor, TaskManager(), resources)  # type: ignore[arg-type]

    result = engine.execute(workflow())

    assert result.success is True
    assert executor.calls == 1
    assert resources.active_lease_count == 0
    assert [event.action.value for event in resources.audit_events()] == [
        "admitted",
        "released",
    ]


def test_workflow_returns_structured_failure_under_critical_pressure() -> None:
    executor = StubExecutor()
    resources = resource_manager(cpu=99)
    engine = WorkflowEngine(executor, TaskManager(), resources)  # type: ignore[arg-type]

    result = engine.execute(workflow())

    assert result.success is False
    assert executor.calls == 0
    assert len(result.results) == 1
    assert result.results[0].action_type == "resource.admission"
    assert result.results[0].error_code == "rejected_pressure"
    assert result.results[0].retryable is True
    assert result.results[0].data["pressure"] == "critical"
    assert resources.active_lease_count == 0


def test_heavy_workflow_is_classified_for_pressure_policy() -> None:
    assert (
        WorkflowEngine._classify_workload(workflow("internet.search"))
        is WorkloadClass.HEAVY
    )


def test_programming_assistant_workflow_is_heavy() -> None:
    assert (
        WorkflowEngine._classify_workload(workflow("domain.programming_assist"))
        is WorkloadClass.HEAVY
    )


def test_wait_workflow_is_light() -> None:
    assert (
        WorkflowEngine._classify_workload(workflow("system.wait"))
        is WorkloadClass.LIGHT
    )


def test_legacy_workflow_without_manager_remains_compatible() -> None:
    executor = StubExecutor()
    engine = WorkflowEngine(executor, TaskManager())  # type: ignore[arg-type]

    result = engine.execute(workflow())

    assert result.success is True
    assert executor.calls == 1


def test_kernel_connects_same_manager_to_workflow_engine() -> None:
    source = (ROOT / "atlas" / "core" / "kernel.py").read_text(encoding="utf-8")
    manager_position = source.index("self.resource_manager = ResourceManager(")
    workflow_position = source.index("self.workflow_engine = WorkflowEngine(")

    assert manager_position < workflow_position
    assert "resource_manager=self.resource_manager" in source


def test_resource_manager_never_controls_external_processes() -> None:
    source = (ROOT / "atlas" / "core" / "resource_manager.py").read_text(
        encoding="utf-8"
    )

    assert "process_iter" not in source
    assert "terminate(" not in source
    assert "kill(" not in source
    assert "subprocess" not in source
    assert "os.environ" not in source
