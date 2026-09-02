from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from atlas.edge import (
    EdgeDeviceStatus,
    EdgeStateStore,
    EnrollmentError,
    ITProvisioningAgent,
)
from atlas.provisioning import DeviceInventory


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


class _Collector:
    def __init__(self, inventory: DeviceInventory) -> None:
        self.inventory = inventory
        self.calls = 0

    def capture(self, packages=()):
        assert packages == ()
        self.calls += 1
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


def _agent(tmp_path, *, collector=None, clock=None) -> ITProvisioningAgent:
    return ITProvisioningAgent(
        store=EdgeStateStore(tmp_path / "edge" / "device.json"),
        collector=collector or _Collector(_inventory()),
        clock=clock or (lambda: NOW),
        token_factory=lambda: "EDGE_TOKEN_123456",
    )


def _enroll(agent: ITProvisioningAgent) -> None:
    challenge = agent.prepare_enrollment("escola-manaus")
    agent.confirm_enrollment(challenge.token, approver_id="ti.responsavel")


def test_random_device_identity_survives_restart(tmp_path) -> None:
    first = _agent(tmp_path)
    second = _agent(tmp_path)

    assert first.state.identity == second.state.identity
    assert first.state.status is EdgeDeviceStatus.UNENROLLED


def test_enrollment_requires_separate_single_use_approval(tmp_path) -> None:
    agent = _agent(tmp_path)

    challenge = agent.prepare_enrollment("escola-manaus")

    assert agent.state.enrollment is None
    state = agent.confirm_enrollment(
        challenge.token,
        approver_id="TI.Responsavel",
    )
    assert state.enrollment is not None
    assert state.enrollment.organization_id == "escola-manaus"
    assert state.enrollment.approver_hash == sha256(
        b"ti.responsavel"
    ).hexdigest()
    with pytest.raises(EnrollmentError, match="já foi utilizado"):
        agent.confirm_enrollment(
            challenge.token,
            approver_id="ti.responsavel",
        )


def test_approver_and_token_are_not_persisted(tmp_path) -> None:
    agent = _agent(tmp_path)
    challenge = agent.prepare_enrollment("escola-manaus")
    agent.confirm_enrollment(challenge.token, approver_id="Nome Privado")

    content = (tmp_path / "edge" / "device.json").read_text(encoding="utf-8")

    assert "Nome Privado" not in content
    assert "nome privado" not in content
    assert challenge.token not in content


def test_expired_enrollment_is_consumed_without_state_change(tmp_path) -> None:
    now = [NOW]
    agent = _agent(tmp_path, clock=lambda: now[0])
    challenge = agent.prepare_enrollment("escola-manaus")
    now[0] += timedelta(minutes=10)

    with pytest.raises(EnrollmentError, match="expirou"):
        agent.confirm_enrollment(challenge.token, approver_id="ti")
    assert agent.state.enrollment is None
    with pytest.raises(EnrollmentError, match="já foi utilizado"):
        agent.confirm_enrollment(challenge.token, approver_id="ti")


def test_inventory_change_cancels_enrollment(tmp_path) -> None:
    collector = _Collector(_inventory())
    agent = _agent(tmp_path, collector=collector)
    challenge = agent.prepare_enrollment("escola-manaus")
    collector.inventory = replace(collector.inventory, os_version="11.1")

    with pytest.raises(PermissionError, match="inventário mudou"):
        agent.confirm_enrollment(challenge.token, approver_id="ti")
    assert agent.state.enrollment is None


def test_heartbeat_requires_enrollment_and_persists_sequence(tmp_path) -> None:
    agent = _agent(tmp_path)
    with pytest.raises(PermissionError, match="não está cadastrado"):
        agent.heartbeat()

    _enroll(agent)
    first = agent.heartbeat()
    second = agent.heartbeat()
    restarted = _agent(tmp_path)
    third = restarted.heartbeat()

    assert [first.sequence, second.sequence, third.sequence] == [1, 2, 3]
    assert third.status is EdgeDeviceStatus.ONLINE
    assert restarted.state.heartbeat_sequence == 3


def test_pause_and_resume_are_persistent_and_idempotent(tmp_path) -> None:
    agent = _agent(tmp_path)
    _enroll(agent)

    paused = agent.pause()
    paused_again = agent.pause()

    assert paused.status is EdgeDeviceStatus.PAUSED
    assert paused_again == paused
    assert _agent(tmp_path).heartbeat().status is EdgeDeviceStatus.PAUSED
    assert _agent(tmp_path).resume().status is EdgeDeviceStatus.ONLINE


def test_concurrent_heartbeats_receive_unique_sequences(tmp_path) -> None:
    agent = _agent(tmp_path)
    _enroll(agent)

    with ThreadPoolExecutor(max_workers=4) as executor:
        sequences = list(executor.map(lambda _: agent.heartbeat().sequence, range(8)))

    assert sorted(sequences) == list(range(1, 9))
    assert agent.state.heartbeat_sequence == 8
