from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from itertools import count

import pytest

from atlas.edge import (
    EdgeAuditOutcome,
    EdgeExecutionService,
    EdgePolicyDenied,
    EdgePolicyEngine,
    EdgePrincipal,
    EdgeProfileService,
    EdgeRole,
    EdgeStateStore,
    EdgeTaskQueue,
    EdgeTaskStore,
    EmployeeOnboardingError,
    EmployeeOnboardingService,
    EmployeeOnboardingStatus,
    EmployeeOnboardingStore,
    EmployeeProfileCatalog,
    GovernedEdgeService,
    ITProvisioningAgent,
    InMemoryEdgeAuditTrail,
    build_edge_policy,
)
from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    PackageRequirement,
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
            device_hash=sha256(b"onboarding-device").hexdigest(),
            winget_available=True,
            captured_at=NOW,
        )

    def capture(self, packages=()):
        del packages
        return self.inventory


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-onboarding",
        display_name="Funcionário gerenciado",
        packages=(PackageRequirement("Google.Chrome", "Chrome"),),
        directories=(DirectoryRequirement("Empresa/Equipe", "Workspace"),),
    )


def _components(tmp_path, *, max_active=20):
    collector = _Collector()
    agent = ITProvisioningAgent(
        store=EdgeStateStore(tmp_path / "device.json"),
        collector=collector,
        clock=lambda: NOW,
        token_factory=lambda: "ENROLL_ONBOARDING_TOKEN",
    )
    enrollment = agent.prepare_enrollment("empresa-manaus")
    agent.confirm_enrollment(enrollment.token, approver_id="ti.cadastro")
    profile = _profile()
    catalog = EmployeeProfileCatalog((profile,))
    planner = ProvisioningPlanner()
    tokens = count(1)
    profiles = EdgeProfileService(
        agent=agent,
        collector=collector,
        planner=planner,
        catalog=catalog,
        clock=lambda: NOW,
        token_factory=lambda: f"PROFILE_ONBOARDING_{next(tokens):04d}",
    )
    queue = EdgeTaskQueue(
        EdgeTaskStore(tmp_path / "tasks.json"),
        clock=lambda: NOW,
    )
    execution = EdgeExecutionService(
        agent=agent,
        profile_service=profiles,
        queue=queue,
        catalog=catalog,
        collector=collector,
        planner=planner,
        executor=ProvisioningExecutor(
            tmp_path / "workspace",
            dry_run=True,
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    audit = InMemoryEdgeAuditTrail()
    governed = GovernedEdgeService(
        agent=agent,
        profile_service=profiles,
        execution_service=execution,
        policy=EdgePolicyEngine(
            (build_edge_policy("empresa-manaus", (profile,)),)
        ),
        audit=audit,
        clock=lambda: NOW,
    )
    store = EmployeeOnboardingStore(tmp_path / "onboardings.json")
    service = EmployeeOnboardingService(
        governed=governed,
        store=store,
        max_active=max_active,
        clock=lambda: NOW,
    )
    return service, governed, store, audit, collector


def _principal(role, identifier):
    return EdgePrincipal(identifier, "empresa-manaus", role)


def _operator():
    return _principal(EdgeRole.OPERATOR, "ti.operador")


def _approver():
    return _principal(EdgeRole.APPROVER, "ti.aprovador")


def _executor():
    return _principal(EdgeRole.EXECUTOR, "ti.executor")


def _start(service, employee="funcionario-um"):
    return service.start(
        _operator(),
        "employee-onboarding",
        employee_reference=employee,
    ).onboarding


def _queue(service, employee="funcionario-um"):
    started = _start(service, employee)
    approved = service.approve(_approver(), started.onboarding_id)
    return service.enqueue(_operator(), approved.onboarding_id)


def test_full_onboarding_finishes_as_simulated(tmp_path) -> None:
    service, _, store, audit, _ = _components(tmp_path)
    queued = _queue(service)

    completed = service.execute(_executor(), queued.onboarding_id)

    assert completed.status is EmployeeOnboardingStatus.SIMULATED
    assert completed.evidence_id is not None
    assert completed.result_status == "dry_run"
    assert store.get(completed.onboarding_id) == completed
    assert any(
        event.outcome is EdgeAuditOutcome.SUCCEEDED
        for event in audit.events
    )


def test_tokens_and_employee_reference_never_reach_store(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    _start(service, employee="maria@empresa.test")
    payload = (tmp_path / "onboardings.json").read_text(encoding="utf-8")

    assert "maria@empresa.test" not in payload
    assert "PROFILE_ONBOARDING" not in payload
    assert "authorization_id" not in payload
    assert "token" not in payload.casefold()


def test_duplicate_active_employee_is_rejected(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    _start(service)

    with pytest.raises(EmployeeOnboardingError, match="Já existe"):
        _start(service)


def test_multiple_employees_keep_independent_approval_sessions(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    first = _start(service, "funcionario-um")
    second = _start(service, "funcionario-dois")

    first_approved = service.approve(_approver(), first.onboarding_id)
    second_approved = service.approve(
        _principal(EdgeRole.APPROVER, "ti.aprovador.dois"),
        second.onboarding_id,
    )

    assert first_approved.status is EmployeeOnboardingStatus.AUTHORIZED
    assert second_approved.status is EmployeeOnboardingStatus.AUTHORIZED


def test_operator_cannot_approve_onboarding(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    started = _start(service)

    with pytest.raises(EdgePolicyDenied, match="role_action_denied"):
        service.approve(_operator(), started.onboarding_id)


def test_approver_cannot_execute_onboarding(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    queued = _queue(service)

    with pytest.raises(EdgePolicyDenied, match="role_action_denied"):
        service.execute(_approver(), queued.onboarding_id)

    assert service.get(_operator(), queued.onboarding_id).status is (
        EmployeeOnboardingStatus.QUEUED
    )


def test_approver_cannot_return_as_executor(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    queued = _queue(service)
    same_person = _principal(EdgeRole.EXECUTOR, "ti.aprovador")

    with pytest.raises(
        EdgePolicyDenied,
        match="executor_must_differ_from_approver",
    ):
        service.execute(same_person, queued.onboarding_id)

    assert service.get(_operator(), queued.onboarding_id).status is (
        EmployeeOnboardingStatus.QUEUED
    )


def test_other_organization_cannot_list_onboardings(tmp_path) -> None:
    service, _, _, audit, _ = _components(tmp_path)
    _start(service)
    outsider = EdgePrincipal("ti.externo", "empresa-outra", EdgeRole.ADMIN)

    with pytest.raises(EdgePolicyDenied, match="cross_organization_denied"):
        service.list(outsider)

    assert audit.events[-1].organization_id == "empresa-manaus"


def test_pending_onboarding_can_be_cancelled_without_task(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    started = _start(service)

    cancelled = service.cancel(_operator(), started.onboarding_id)

    assert cancelled.status is EmployeeOnboardingStatus.CANCELLED
    assert cancelled.task_id is None


def test_queued_onboarding_cancels_underlying_task(tmp_path) -> None:
    service, governed, _, _, _ = _components(tmp_path)
    queued = _queue(service)

    cancelled = service.cancel(_operator(), queued.onboarding_id)
    task = next(
        task
        for task in governed.list_tasks(_operator())
        if task.task_id == queued.task_id
    )

    assert cancelled.status is EmployeeOnboardingStatus.CANCELLED
    assert task.status.value == "cancelled"


def test_lost_approval_session_requires_new_plan(tmp_path) -> None:
    service, governed, store, _, _ = _components(tmp_path)
    started = _start(service)
    restarted = EmployeeOnboardingService(
        governed=governed,
        store=store,
        clock=lambda: NOW,
    )

    records = restarted.reconcile(_operator())

    assert records[0].onboarding_id == started.onboarding_id
    assert records[0].status is EmployeeOnboardingStatus.ACTION_REQUIRED
    assert records[0].error_code == "approval_session_lost"


def test_lost_authorization_session_requires_new_plan(tmp_path) -> None:
    service, governed, store, _, _ = _components(tmp_path)
    started = _start(service)
    authorized = service.approve(_approver(), started.onboarding_id)
    restarted = EmployeeOnboardingService(
        governed=governed,
        store=store,
        clock=lambda: NOW,
    )

    with pytest.raises(EmployeeOnboardingError, match="foi perdida"):
        restarted.enqueue(_operator(), authorized.onboarding_id)

    assert store.get(authorized.onboarding_id).status is (
        EmployeeOnboardingStatus.ACTION_REQUIRED
    )


def test_action_required_plan_can_be_recreated_with_same_reference(
    tmp_path,
) -> None:
    service, governed, store, _, _ = _components(tmp_path)
    started = _start(service)
    restarted = EmployeeOnboardingService(
        governed=governed,
        store=store,
        clock=lambda: NOW,
    )
    restarted.reconcile(_operator())

    result = restarted.restart_plan(
        _operator(),
        started.onboarding_id,
        employee_reference="funcionario-um",
    )

    assert result.onboarding.status is (
        EmployeeOnboardingStatus.AWAITING_APPROVAL
    )
    assert result.onboarding.revision > started.revision


def test_replan_rejects_different_employee_reference(tmp_path) -> None:
    service, governed, store, _, _ = _components(tmp_path)
    started = _start(service)
    restarted = EmployeeOnboardingService(
        governed=governed,
        store=store,
        clock=lambda: NOW,
    )
    restarted.reconcile(_operator())

    with pytest.raises(PermissionError, match="não pertence"):
        restarted.restart_plan(
            _operator(),
            started.onboarding_id,
            employee_reference="outra-pessoa",
        )


def test_queued_onboarding_survives_coordinator_restart(tmp_path) -> None:
    service, governed, store, _, _ = _components(tmp_path)
    queued = _queue(service)
    restarted = EmployeeOnboardingService(
        governed=governed,
        store=store,
        clock=lambda: NOW,
    )

    reconciled = restarted.reconcile(_operator())
    completed = restarted.execute(_executor(), queued.onboarding_id)

    assert reconciled[0].status is EmployeeOnboardingStatus.QUEUED
    assert completed.status is EmployeeOnboardingStatus.SIMULATED


def test_reconcile_is_idempotent_for_unchanged_queued_task(tmp_path) -> None:
    service, _, store, _, _ = _components(tmp_path)
    queued = _queue(service)

    first = service.reconcile(_operator())[0]
    second = service.reconcile(_operator())[0]

    assert first.revision == queued.revision
    assert second.revision == queued.revision
    assert store.get(queued.onboarding_id).revision == queued.revision


def test_inventory_failure_is_reflected_in_onboarding(tmp_path) -> None:
    service, _, store, _, collector = _components(tmp_path)
    queued = _queue(service)
    collector.inventory = replace(collector.inventory, os_version="11.1")

    with pytest.raises(PermissionError, match="inventário mudou"):
        service.execute(_executor(), queued.onboarding_id)

    failed = store.get(queued.onboarding_id)
    assert failed.status is EmployeeOnboardingStatus.FAILED
    assert failed.error_code == "permission_denied"


def test_report_counts_active_and_terminal_states(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path)
    _start(service, "funcionario-ativo")
    simulated = _queue(service, "funcionario-simulado")
    service.execute(_executor(), simulated.onboarding_id)
    cancelled = _start(service, "funcionario-cancelado")
    service.cancel(_operator(), cancelled.onboarding_id)

    report = service.report(
        _principal(EdgeRole.AUDITOR, "ti.auditor"),
    )

    assert report.total == 3
    assert report.active == 1
    assert report.simulated == 1
    assert report.cancelled == 1


def test_active_workflow_limit_is_enforced(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path, max_active=1)
    _start(service, "funcionario-um")

    with pytest.raises(OverflowError, match="muitos onboardings ativos"):
        _start(service, "funcionario-dois")


def test_terminal_workflow_releases_active_capacity(tmp_path) -> None:
    service, _, _, _, _ = _components(tmp_path, max_active=1)
    first = _start(service, "funcionario-um")
    service.cancel(_operator(), first.onboarding_id)

    second = _start(service, "funcionario-dois")

    assert second.status is EmployeeOnboardingStatus.AWAITING_APPROVAL


def test_concurrent_approval_consumes_transient_token_once(tmp_path) -> None:
    service, _, store, _, _ = _components(tmp_path)
    started = _start(service)
    approvers = (
        _principal(EdgeRole.APPROVER, "ti.aprovador.um"),
        _principal(EdgeRole.APPROVER, "ti.aprovador.dois"),
    )

    def approve(principal):
        try:
            return service.approve(principal, started.onboarding_id)
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(approve, approvers))

    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert store.get(started.onboarding_id).status is (
        EmployeeOnboardingStatus.AUTHORIZED
    )


def test_concurrent_execution_runs_task_only_once(tmp_path) -> None:
    service, _, store, _, _ = _components(tmp_path)
    queued = _queue(service)
    executors = (
        _principal(EdgeRole.EXECUTOR, "ti.executor.um"),
        _principal(EdgeRole.EXECUTOR, "ti.executor.dois"),
    )

    def execute(principal):
        try:
            return service.execute(principal, queued.onboarding_id)
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(execute, executors))

    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert store.get(queued.onboarding_id).status is (
        EmployeeOnboardingStatus.SIMULATED
    )
