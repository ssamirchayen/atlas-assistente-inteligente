from datetime import datetime, timezone
from hashlib import sha256

import pytest

from atlas.edge import (
    EdgeAction,
    EdgeAuditOutcome,
    EdgeExecutionService,
    EdgePolicyDenied,
    EdgePolicyEngine,
    EdgePrincipal,
    EdgeProfileService,
    EdgeRole,
    EdgeStateStore,
    EdgeTaskQueue,
    EdgeTaskStatus,
    EdgeTaskStore,
    EmployeeProfileCatalog,
    GovernedEdgeService,
    ITProvisioningAgent,
    InMemoryEdgeAuditTrail,
    build_edge_policy,
)
from atlas.provisioning import (
    CommandResult,
    DeviceInventory,
    DirectoryRequirement,
    ManagedSettingRequirement,
    ManagedSettingType,
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
            device_hash=sha256(b"governed-device").hexdigest(),
            winget_available=True,
            captured_at=NOW,
        )

    def capture(self, packages=()):
        del packages
        return self.inventory


class _Runner:
    def run(self, arguments, *, timeout):
        del arguments, timeout
        return CommandResult(return_code=0, stdout="ok", stderr="")


class _SettingsAdapter:
    def apply(self, step):
        del step
        return "Configuração corporativa aplicada."


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-governed",
        display_name="Funcionário governado",
        packages=(PackageRequirement("Google.Chrome", "Chrome"),),
        directories=(DirectoryRequirement("Empresa/Equipe", "Workspace"),),
        settings=(
            ManagedSettingRequirement(
                setting_id="browser-home",
                setting_type=ManagedSettingType.BROWSER,
                description="Página inicial",
                parameters={
                    "browser": "chrome",
                    "homepage": "https://portal.empresa.test",
                },
            ),
        ),
    )


def _components(tmp_path, *, dry_run=True, allow_real=False, audit=None):
    collector = _Collector()
    agent = ITProvisioningAgent(
        store=EdgeStateStore(tmp_path / "device.json"),
        collector=collector,
        clock=lambda: NOW,
        token_factory=lambda: "ENROLL_GOVERNED_TOKEN",
    )
    enrollment = agent.prepare_enrollment("empresa-manaus")
    agent.confirm_enrollment(enrollment.token, approver_id="ti.cadastro")
    profile = _profile()
    catalog = EmployeeProfileCatalog((profile,))
    planner = ProvisioningPlanner()
    profiles = EdgeProfileService(
        agent=agent,
        collector=collector,
        planner=planner,
        catalog=catalog,
        clock=lambda: NOW,
        token_factory=lambda: "PROFILE_GOVERNED_TOKEN",
    )
    execution = EdgeExecutionService(
        agent=agent,
        profile_service=profiles,
        queue=EdgeTaskQueue(
            EdgeTaskStore(tmp_path / "tasks.json"),
            clock=lambda: NOW,
        ),
        catalog=catalog,
        collector=collector,
        planner=planner,
        executor=ProvisioningExecutor(
            tmp_path / "workspace",
            runner=_Runner(),
            winget_path="winget.exe",
            dry_run=dry_run,
            settings_adapter=_SettingsAdapter(),
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
    )
    audit = audit or InMemoryEdgeAuditTrail()
    governed = GovernedEdgeService(
        agent=agent,
        profile_service=profiles,
        execution_service=execution,
        policy=EdgePolicyEngine(
            (
                build_edge_policy(
                    "empresa-manaus",
                    (profile,),
                    allow_real_execution=allow_real,
                ),
            )
        ),
        audit=audit,
        clock=lambda: NOW,
    )
    return governed, audit, profiles


def _principal(role, principal_id):
    return EdgePrincipal(principal_id, "empresa-manaus", role)


def _enqueue(governed):
    operator = _principal(EdgeRole.OPERATOR, "ti.operador")
    approver = _principal(EdgeRole.APPROVER, "ti.aprovador")
    challenge = governed.prepare_configuration(
        operator,
        "employee-governed",
        employee_reference="funcionario-confidencial",
    )
    authorization = governed.authorize_configuration(approver, challenge.token)
    return governed.enqueue_authorization(
        operator,
        authorization.authorization_id,
    )


def test_governed_flow_separates_operator_approver_and_executor(tmp_path) -> None:
    governed, audit, _ = _components(tmp_path)
    task = _enqueue(governed)

    result = governed.execute_task(
        _principal(EdgeRole.EXECUTOR, "ti.executor"),
        task.task_id,
    )

    assert result.task.status is EdgeTaskStatus.SIMULATED
    succeeded = [
        event
        for event in audit.events
        if event.outcome is EdgeAuditOutcome.SUCCEEDED
    ]
    assert {event.action for event in succeeded} >= {
        EdgeAction.PLAN_PREPARE,
        EdgeAction.PLAN_APPROVE,
        EdgeAction.TASK_ENQUEUE,
        EdgeAction.TASK_EXECUTE,
    }


def test_operator_cannot_approve_plan(tmp_path) -> None:
    governed, audit, _ = _components(tmp_path)
    operator = _principal(EdgeRole.OPERATOR, "ti.operador")
    challenge = governed.prepare_configuration(
        operator,
        "employee-governed",
        employee_reference="funcionario-um",
    )

    with pytest.raises(EdgePolicyDenied) as error:
        governed.authorize_configuration(operator, challenge.token)

    assert error.value.reason_code == "role_action_denied"
    assert audit.events[-1].outcome is EdgeAuditOutcome.DENIED


def test_principal_from_other_company_cannot_list_local_profiles(tmp_path) -> None:
    governed, audit, _ = _components(tmp_path)
    intruder = EdgePrincipal("ti.intruso", "empresa-outra", EdgeRole.ADMIN)

    with pytest.raises(EdgePolicyDenied) as error:
        governed.list_profiles(intruder)

    assert error.value.reason_code == "cross_organization_denied"
    assert audit.events[-1].organization_id == "empresa-manaus"


def test_approver_cannot_execute_the_task_they_approved(tmp_path) -> None:
    governed, _, _ = _components(tmp_path)
    task = _enqueue(governed)
    same_person_as_executor = _principal(EdgeRole.EXECUTOR, "ti.aprovador")

    with pytest.raises(EdgePolicyDenied) as error:
        governed.execute_task(same_person_as_executor, task.task_id)

    assert error.value.reason_code == "executor_must_differ_from_approver"


def test_auditor_can_read_audit_but_cannot_execute(tmp_path) -> None:
    governed, _, _ = _components(tmp_path)
    task = _enqueue(governed)
    auditor = _principal(EdgeRole.AUDITOR, "ti.auditor")

    events = governed.list_audit(auditor)
    with pytest.raises(EdgePolicyDenied, match="role_action_denied"):
        governed.execute_task(auditor, task.task_id)

    assert events
    assert all(event.organization_id == "empresa-manaus" for event in events)


def test_real_execution_is_blocked_even_when_executor_is_configured(tmp_path) -> None:
    governed, _, _ = _components(tmp_path, dry_run=False, allow_real=False)
    task = _enqueue(governed)

    with pytest.raises(EdgePolicyDenied) as error:
        governed.execute_task(
            _principal(EdgeRole.EXECUTOR, "ti.executor"),
            task.task_id,
        )

    assert error.value.reason_code == "real_execution_disabled"


def test_real_execution_requires_policy_and_executor_role(tmp_path) -> None:
    governed, _, _ = _components(tmp_path, dry_run=False, allow_real=True)
    task = _enqueue(governed)

    result = governed.execute_task(
        _principal(EdgeRole.EXECUTOR, "ti.executor"),
        task.task_id,
    )

    assert result.task.status is EdgeTaskStatus.SUCCEEDED


def test_operator_can_cancel_queued_task_and_audit_result(tmp_path) -> None:
    governed, audit, _ = _components(tmp_path)
    task = _enqueue(governed)

    cancelled = governed.cancel_task(
        _principal(EdgeRole.OPERATOR, "ti.operador"),
        task.task_id,
    )

    assert cancelled.status is EdgeTaskStatus.CANCELLED
    assert audit.events[-1].reason_code == "task_cancelled"


def test_task_listing_returns_only_principal_organization(tmp_path) -> None:
    governed, _, _ = _components(tmp_path)
    _enqueue(governed)

    tasks = governed.list_tasks(
        _principal(EdgeRole.AUDITOR, "ti.auditor"),
    )

    assert len(tasks) == 1
    assert tasks[0].organization_id == "empresa-manaus"


class _UnavailableAudit:
    def record(self, event):
        del event
        raise RuntimeError("audit unavailable")

    def query(self, organization_id, *, limit=100):
        del organization_id, limit
        return ()


def test_mutation_fails_closed_when_audit_is_unavailable(tmp_path) -> None:
    governed, _, profiles = _components(tmp_path, audit=_UnavailableAudit())

    with pytest.raises(RuntimeError, match="audit unavailable"):
        governed.prepare_configuration(
            _principal(EdgeRole.OPERATOR, "ti.operador"),
            "employee-governed",
            employee_reference="funcionario-um",
        )

    with pytest.raises(ValueError, match="não existe"):
        profiles.inspect_pending_configuration("PROFILE_GOVERNED_TOKEN")


def test_audit_never_contains_employee_reference_or_actor_id(tmp_path) -> None:
    governed, audit, _ = _components(tmp_path)
    _enqueue(governed)
    serialized = repr(audit.events)

    assert "funcionario-confidencial" not in serialized
    assert "ti.operador" not in serialized
