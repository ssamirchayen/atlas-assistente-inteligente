from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from atlas.edge import (
    EdgeExecutionService,
    EdgeProfileService,
    EdgeStateStore,
    EdgeTaskQueue,
    EdgeTaskStatus,
    EdgeTaskStore,
    EmployeeProfileCatalog,
    ITProvisioningAgent,
)
from atlas.provisioning import (
    DeviceInventory,
    ManagedSettingRequirement,
    ManagedSettingType,
    ProvisioningExecutor,
    ProvisioningPlanner,
    ProvisioningProfile,
)


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


class _Collector:
    def __init__(self) -> None:
        self.inventory = DeviceInventory(
            os_name="Windows",
            os_version="11",
            architecture="AMD64",
            device_hash=sha256(b"device-stage3").hexdigest(),
            winget_available=True,
            captured_at=NOW,
        )

    def capture(self, packages=()):
        del packages
        return self.inventory


class _Adapter:
    def __init__(self) -> None:
        self.calls = []

    def apply(self, step):
        self.calls.append(step)
        return "Configuração corporativa aplicada."


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-managed",
        display_name="Funcionário gerenciado",
        settings=(
            ManagedSettingRequirement(
                setting_id="browser-home",
                setting_type=ManagedSettingType.BROWSER,
                description="Definir página corporativa",
                parameters={
                    "browser": "chrome",
                    "homepage": "https://portal.empresa.test",
                },
            ),
        ),
    )


def _components(tmp_path, *, dry_run=True, adapter=None):
    collector = _Collector()
    agent = ITProvisioningAgent(
        store=EdgeStateStore(tmp_path / "device.json"),
        collector=collector,
        clock=lambda: NOW,
        token_factory=lambda: "ENROLL_STAGE3_TOKEN",
    )
    enrollment = agent.prepare_enrollment("empresa-manaus")
    agent.confirm_enrollment(enrollment.token, approver_id="ti.cadastro")
    catalog = EmployeeProfileCatalog((_profile(),))
    planner = ProvisioningPlanner()
    profiles = EdgeProfileService(
        agent=agent,
        collector=collector,
        planner=planner,
        catalog=catalog,
        clock=lambda: NOW,
        token_factory=lambda: "PROFILE_STAGE3_TOKEN",
    )
    queue = EdgeTaskQueue(
        EdgeTaskStore(tmp_path / "tasks.json"),
        clock=lambda: NOW,
    )
    service = EdgeExecutionService(
        agent=agent,
        profile_service=profiles,
        queue=queue,
        catalog=catalog,
        collector=collector,
        planner=planner,
        executor=ProvisioningExecutor(
            tmp_path / "workspace",
            dry_run=dry_run,
            settings_adapter=adapter,
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    return service, profiles, queue, agent, collector


def _authorize(profiles: EdgeProfileService):
    challenge = profiles.prepare_configuration(
        "employee-managed",
        employee_reference="funcionario-stage3",
        requester_id="ti.operador",
    )
    return profiles.authorize_configuration(
        challenge.token,
        approver_id="ti.responsavel",
    )


def test_authorization_is_consumed_once_into_persistent_queue(tmp_path) -> None:
    service, profiles, queue, _, _ = _components(tmp_path)
    authorization = _authorize(profiles)

    task = service.enqueue_authorization(authorization.authorization_id)

    assert queue.get(task.task_id).status is EdgeTaskStatus.QUEUED
    with pytest.raises(ValueError, match="já foi utilizada"):
        service.enqueue_authorization(authorization.authorization_id)


def test_supervised_dry_run_completes_without_adapter_call(tmp_path) -> None:
    adapter = _Adapter()
    service, profiles, _, _, _ = _components(tmp_path, adapter=adapter)
    task = service.enqueue_authorization(_authorize(profiles).authorization_id)

    result = service.execute_task(task.task_id)

    assert result.task.status is EdgeTaskStatus.SIMULATED
    assert result.evidence.dry_run is True
    assert adapter.calls == []


def test_real_execution_uses_reviewed_adapter_only(tmp_path) -> None:
    adapter = _Adapter()
    service, profiles, _, _, _ = _components(
        tmp_path,
        dry_run=False,
        adapter=adapter,
    )
    task = service.enqueue_authorization(_authorize(profiles).authorization_id)

    result = service.execute_task(task.task_id)

    assert result.task.status is EdgeTaskStatus.SUCCEEDED
    assert len(adapter.calls) == 1


def test_inventory_change_fails_task_before_executor(tmp_path) -> None:
    adapter = _Adapter()
    service, profiles, queue, _, collector = _components(
        tmp_path,
        dry_run=False,
        adapter=adapter,
    )
    task = service.enqueue_authorization(_authorize(profiles).authorization_id)
    collector.inventory = replace(collector.inventory, os_version="11.1")

    with pytest.raises(PermissionError, match="inventário mudou"):
        service.execute_task(task.task_id)
    assert queue.get(task.task_id).status is EdgeTaskStatus.FAILED
    assert queue.get(task.task_id).error_code == "permission_denied"
    assert adapter.calls == []


def test_paused_agent_cannot_claim_task(tmp_path) -> None:
    service, profiles, queue, agent, _ = _components(tmp_path)
    task = service.enqueue_authorization(_authorize(profiles).authorization_id)
    agent.pause()

    with pytest.raises(PermissionError, match="pausado"):
        service.execute_task(task.task_id)
    assert queue.get(task.task_id).status is EdgeTaskStatus.QUEUED


def test_tampered_valid_step_is_rejected_against_profile(tmp_path) -> None:
    service, profiles, queue, _, _ = _components(tmp_path)
    task = service.enqueue_authorization(_authorize(profiles).authorization_id)
    path = tmp_path / "tasks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tasks"][0]["plan"]["steps"][0]["parameters"]["homepage"] = (
        "https://outro.empresa.test"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    reloaded_queue = EdgeTaskQueue(EdgeTaskStore(path), clock=lambda: NOW)
    reloaded = EdgeExecutionService(
        agent=service._agent,
        profile_service=profiles,
        queue=reloaded_queue,
        catalog=service._catalog,
        collector=service._collector,
        planner=service._planner,
        executor=service._executor,
        clock=lambda: NOW,
    )
    with pytest.raises(PermissionError, match="não conferem"):
        reloaded.execute_task(task.task_id)
    assert reloaded_queue.get(task.task_id).status is EdgeTaskStatus.FAILED


def test_operator_can_cancel_queued_task(tmp_path) -> None:
    service, profiles, _, _, _ = _components(tmp_path)
    task = service.enqueue_authorization(_authorize(profiles).authorization_id)

    cancelled = service.cancel_task(task.task_id)

    assert cancelled.status is EdgeTaskStatus.CANCELLED
