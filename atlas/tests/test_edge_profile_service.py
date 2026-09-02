from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from atlas.edge import (
    EdgeProfileError,
    EdgeProfileService,
    EdgeStateStore,
    EmployeeProfileCatalog,
    ITProvisioningAgent,
)
from atlas.provisioning import (
    DeviceInventory,
    DirectoryRequirement,
    PackageRequirement,
    ProvisioningPlanner,
    ProvisioningProfile,
)


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


class _Collector:
    def __init__(self, inventory: DeviceInventory) -> None:
        self.inventory = inventory
        self.calls: list[tuple[PackageRequirement, ...]] = []

    def capture(self, packages=()):
        self.calls.append(tuple(packages))
        return self.inventory


def _inventory() -> DeviceInventory:
    return DeviceInventory(
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        device_hash=sha256(b"test-device").hexdigest(),
        winget_available=True,
        captured_at=NOW,
    )


def _profile() -> ProvisioningProfile:
    return ProvisioningProfile(
        profile_id="employee-sales",
        display_name="Equipe comercial",
        packages=(
            PackageRequirement(
                package_id="Google.Chrome",
                display_name="Google Chrome",
            ),
        ),
        directories=(
            DirectoryRequirement(
                relative_path="Empresa/Comercial",
                description="Criar workspace comercial",
            ),
        ),
    )


def _components(tmp_path, *, clock=None, enroll=True, token_factory=None):
    collector = _Collector(_inventory())
    agent = ITProvisioningAgent(
        store=EdgeStateStore(tmp_path / "edge" / "device.json"),
        collector=collector,
        clock=clock or (lambda: NOW),
        token_factory=lambda: "ENROLL_TOKEN_123456",
    )
    if enroll:
        challenge = agent.prepare_enrollment("empresa-manaus")
        agent.confirm_enrollment(challenge.token, approver_id="ti.cadastro")
    service = EdgeProfileService(
        agent=agent,
        collector=collector,
        planner=ProvisioningPlanner(),
        catalog=EmployeeProfileCatalog((_profile(),)),
        clock=clock or (lambda: NOW),
        token_factory=token_factory or (lambda: "PROFILE_TOKEN_123456"),
    )
    return service, agent, collector


def _prepare(service: EdgeProfileService):
    return service.prepare_configuration(
        "employee-sales",
        employee_reference="maria@empresa.test",
        requester_id="ti.operador",
    )


def test_planning_requires_enrolled_active_device(tmp_path) -> None:
    service, _, _ = _components(tmp_path, enroll=False)
    with pytest.raises(PermissionError, match="não está cadastrado"):
        _prepare(service)

    active, agent, _ = _components(tmp_path / "paused")
    agent.pause()
    with pytest.raises(PermissionError, match="pausado"):
        _prepare(active)


def test_prepare_builds_allowlisted_plan_and_hashes_private_data(tmp_path) -> None:
    service, _, collector = _components(tmp_path)

    challenge = _prepare(service)
    payload = json.dumps(challenge.preview.as_payload())

    assert challenge.preview.plan.profile_id == "employee-sales"
    assert len(challenge.preview.plan.steps) == 2
    assert "Google.Chrome" in payload
    assert "maria@empresa.test" not in payload
    assert "ti.operador" not in payload
    assert challenge.token not in payload
    assert collector.calls[-1] == _profile().packages


def test_unknown_profile_is_blocked_before_inventory(tmp_path) -> None:
    service, _, collector = _components(tmp_path)
    calls_before = len(collector.calls)

    with pytest.raises(ValueError, match="não autorizado"):
        service.prepare_configuration(
            "profile-created-by-user",
            employee_reference="funcionario",
            requester_id="ti",
        )

    assert len(collector.calls) == calls_before


def test_requester_cannot_approve_own_plan_and_token_is_consumed(
    tmp_path,
) -> None:
    service, _, _ = _components(tmp_path)
    challenge = _prepare(service)

    with pytest.raises(PermissionError, match="próprio plano"):
        service.authorize_configuration(
            challenge.token,
            approver_id="TI.OPERADOR",
        )
    with pytest.raises(EdgeProfileError, match="já foi utilizado"):
        service.authorize_configuration(
            challenge.token,
            approver_id="ti.responsavel",
        )


def test_expired_plan_is_rejected_and_consumed(tmp_path) -> None:
    now = [NOW]
    service, _, _ = _components(tmp_path, clock=lambda: now[0])
    challenge = _prepare(service)
    now[0] += timedelta(minutes=10)

    with pytest.raises(EdgeProfileError, match="expirou"):
        service.authorize_configuration(
            challenge.token,
            approver_id="ti.responsavel",
        )
    with pytest.raises(EdgeProfileError, match="já foi utilizado"):
        service.authorize_configuration(
            challenge.token,
            approver_id="ti.responsavel",
        )


def test_inventory_change_invalidates_plan(tmp_path) -> None:
    service, _, collector = _components(tmp_path)
    challenge = _prepare(service)
    collector.inventory = replace(collector.inventory, os_version="11.1")

    with pytest.raises(PermissionError, match="computador mudou"):
        service.authorize_configuration(
            challenge.token,
            approver_id="ti.responsavel",
        )


def test_authorized_plan_is_sanitized_and_single_use(tmp_path) -> None:
    service, _, _ = _components(tmp_path)
    challenge = _prepare(service)

    authorization = service.authorize_configuration(
        challenge.token,
        approver_id="ti.responsavel",
    )
    payload = json.dumps(authorization.as_payload())

    assert authorization.authorization_id.startswith("edgeauth_")
    assert authorization.valid_until == NOW + timedelta(minutes=15)
    assert '"status": "authorized"' in payload
    assert "ti.responsavel" not in payload
    assert challenge.token not in payload
    with pytest.raises(EdgeProfileError, match="já foi utilizado"):
        service.authorize_configuration(
            challenge.token,
            approver_id="outro.responsavel",
        )


def test_multiple_pending_plans_can_be_approved_independently(tmp_path) -> None:
    tokens = iter(("PROFILE_TOKEN_FIRST", "PROFILE_TOKEN_SECOND"))
    service, _, _ = _components(tmp_path, token_factory=lambda: next(tokens))
    first = _prepare(service)
    second = _prepare(service)

    first_authorized = service.authorize_configuration(
        first.token,
        approver_id="ti.responsavel.um",
    )
    second_authorized = service.authorize_configuration(
        second.token,
        approver_id="ti.responsavel.dois",
    )
    assert first_authorized.preview.request_id == first.preview.request_id
    assert second_authorized.preview.request_id == second.preview.request_id


def test_invalid_token_factory_does_not_create_pending_plan(tmp_path) -> None:
    collector = _Collector(_inventory())
    _, agent, _ = _components(tmp_path / "agent")
    service = EdgeProfileService(
        agent=agent,
        collector=collector,
        planner=ProvisioningPlanner(),
        catalog=EmployeeProfileCatalog((_profile(),)),
        clock=lambda: NOW,
        token_factory=lambda: "invalid token",
    )

    with pytest.raises(EdgeProfileError, match="token inválido"):
        _prepare(service)
