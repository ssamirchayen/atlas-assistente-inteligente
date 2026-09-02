from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from atlas.edge import (
    AuthorizedEdgePlan,
    EdgeConfigurationPreview,
    EdgeTaskQueue,
    EdgeTaskStatus,
    EdgeTaskStore,
    EdgeTaskStoreError,
    hash_private_reference,
    profile_digest,
)
from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    ProvisioningEvidence,
    ProvisioningPlan,
    ProvisioningProfile,
    ProvisioningStatus,
    ProvisioningStep,
    ProvisioningStepType,
)


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-sales",
        display_name="Equipe comercial",
        directories=(
            DirectoryRequirement("Empresa/Comercial", "Criar workspace"),
        ),
    )


def _plan() -> ProvisioningPlan:
    inventory = DeviceInventory(
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        device_hash=sha256(b"device").hexdigest(),
        winget_available=True,
        captured_at=NOW,
    )
    return ProvisioningPlan(
        profile_id="employee-sales",
        inventory_fingerprint=inventory.fingerprint(),
        steps=(
            ProvisioningStep(
                step_id="folder-1",
                step_type=ProvisioningStepType.CREATE_DIRECTORY,
                description="Criar workspace",
                parameters={"relative_path": "Empresa/Comercial"},
                reversible=True,
            ),
        ),
        plan_id="plan-stage3",
        created_at=NOW,
    )


def _authorization() -> AuthorizedEdgePlan:
    profile = _profile()
    preview = EdgeConfigurationPreview(
        device_id="edge_0123456789abcdef0123456789abcdef",
        organization_id="empresa-manaus",
        profile_name=profile.display_name,
        profile_digest=profile_digest(profile),
        employee_reference_hash=hash_private_reference(
            "employee-private-value",
            "employee",
        ),
        requester_hash=hash_private_reference(
            "requester-private-value",
            "requester",
        ),
        plan=_plan(),
        created_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=9),
        request_id="edgeplan_0123456789abcdef0123456789abcdef",
    )
    return AuthorizedEdgePlan(
        preview=preview,
        approver_hash=hash_private_reference(
            "approver-private-value",
            "approver",
        ),
        authorized_at=NOW,
        valid_until=NOW + timedelta(minutes=15),
        authorization_id="edgeauth_0123456789abcdef0123456789abcdef",
    )


def _evidence(plan: ProvisioningPlan) -> ProvisioningEvidence:
    return ProvisioningEvidence(
        evidence_id="evidence-stage3",
        plan_id=plan.plan_id,
        plan_digest=plan.digest(),
        device_hash=sha256(b"device").hexdigest(),
        status=ProvisioningStatus.DRY_RUN,
        steps=(),
        dry_run=True,
        started_at=NOW,
        finished_at=NOW,
    )


def test_queue_persists_and_enqueue_is_idempotent(tmp_path) -> None:
    store = EdgeTaskStore(tmp_path / "tasks.json")
    queue = EdgeTaskQueue(store, clock=lambda: NOW)

    first = queue.enqueue(_authorization())
    second = queue.enqueue(_authorization())
    restarted = EdgeTaskQueue(store, clock=lambda: NOW)

    assert second == first
    assert restarted.get(first.task_id) == first
    content = (tmp_path / "tasks.json").read_text(encoding="utf-8")
    assert "employee-private-value" not in content
    assert "requester-private-value" not in content
    assert "approver-private-value" not in content


def test_claim_and_complete_store_sanitized_result(tmp_path) -> None:
    queue = EdgeTaskQueue(EdgeTaskStore(tmp_path / "tasks.json"), clock=lambda: NOW)
    task = queue.enqueue(_authorization())

    running = queue.claim(task.task_id)
    completed = queue.complete(task.task_id, _evidence(task.plan))

    assert running.status is EdgeTaskStatus.RUNNING
    assert running.attempts == 1
    assert completed.status is EdgeTaskStatus.SIMULATED
    assert completed.evidence_id == "evidence-stage3"


def test_expired_task_fails_closed(tmp_path) -> None:
    now = [NOW]
    queue = EdgeTaskQueue(
        EdgeTaskStore(tmp_path / "tasks.json"),
        clock=lambda: now[0],
    )
    task = queue.enqueue(_authorization())
    now[0] += timedelta(minutes=15)

    with pytest.raises(PermissionError, match="expirou"):
        queue.claim(task.task_id)
    assert queue.get(task.task_id).status is EdgeTaskStatus.EXPIRED


def test_running_task_returns_to_queue_after_restart(tmp_path) -> None:
    store = EdgeTaskStore(tmp_path / "tasks.json")
    queue = EdgeTaskQueue(store, clock=lambda: NOW)
    task = queue.enqueue(_authorization())
    queue.claim(task.task_id)

    restarted = EdgeTaskQueue(store, clock=lambda: NOW + timedelta(seconds=1))
    recovered = restarted.get(task.task_id)

    assert recovered.status is EdgeTaskStatus.QUEUED
    assert recovered.recovery_count == 1
    assert recovered.error_code == "interrupted_recovered"


def test_cancel_only_accepts_queued_task(tmp_path) -> None:
    queue = EdgeTaskQueue(EdgeTaskStore(tmp_path / "tasks.json"), clock=lambda: NOW)
    task = queue.enqueue(_authorization())

    cancelled = queue.cancel(task.task_id)

    assert cancelled.status is EdgeTaskStatus.CANCELLED
    with pytest.raises(ValueError, match="espera"):
        queue.cancel(task.task_id)


def test_corrupt_or_oversized_store_fails_closed(tmp_path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(EdgeTaskStoreError, match="corrompido"):
        EdgeTaskStore(path).load()

    path.write_text(json.dumps({"schema_version": 1, "tasks": []}), encoding="utf-8")
    with pytest.raises(EdgeTaskStoreError, match="excede"):
        EdgeTaskStore(path, max_bytes=4).load()


def test_tampered_unknown_step_type_is_rejected_on_load(tmp_path) -> None:
    store = EdgeTaskStore(tmp_path / "tasks.json")
    queue = EdgeTaskQueue(store, clock=lambda: NOW)
    queue.enqueue(_authorization())
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["tasks"][0]["plan"]["steps"][0]["step_type"] = "run_shell"
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EdgeTaskStoreError, match="corrompido"):
        store.load()


def test_concurrent_claim_allows_only_one_runner(tmp_path) -> None:
    queue = EdgeTaskQueue(EdgeTaskStore(tmp_path / "tasks.json"), clock=lambda: NOW)
    task = queue.enqueue(_authorization())

    def claim_once():
        try:
            return queue.claim(task.task_id).status.value
        except ValueError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim_once(), range(2)))

    assert sorted(results) == ["blocked", "running"]
