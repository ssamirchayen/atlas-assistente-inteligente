from datetime import datetime, timezone

import pytest

from atlas.edge import (
    DeviceEnrollment,
    DeviceIdentity,
    EdgeDeviceStatus,
    EdgeHeartbeat,
    EdgePersistentState,
)


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)
DIGEST = "a" * 64


def _identity() -> DeviceIdentity:
    return DeviceIdentity(device_id=f"edge_{'1' * 32}", created_at=NOW)


def _enrollment() -> DeviceEnrollment:
    return DeviceEnrollment(
        organization_id="escola-manaus",
        inventory_fingerprint=DIGEST,
        approver_hash="b" * 64,
        enrolled_at=NOW,
    )


def test_persistent_state_round_trip_keeps_only_allowed_fields() -> None:
    state = EdgePersistentState(
        identity=_identity(),
        enrollment=_enrollment(),
        heartbeat_sequence=2,
        last_heartbeat_at=NOW,
    )

    restored = EdgePersistentState.from_dict(state.as_dict())

    assert restored == state
    serialized = str(state.as_dict()).casefold()
    for forbidden in ("hostname", "serial", "username", "ip_address", "token"):
        assert forbidden not in serialized


def test_unenrolled_state_rejects_operational_sequence() -> None:
    with pytest.raises(ValueError, match="não cadastrado"):
        EdgePersistentState(identity=_identity(), heartbeat_sequence=1)


def test_heartbeat_payload_is_sanitized() -> None:
    heartbeat = EdgeHeartbeat(
        device_id=_identity().device_id,
        organization_id="escola-manaus",
        sequence=1,
        status=EdgeDeviceStatus.ONLINE,
        agent_version="0.1.0",
        inventory_fingerprint=DIGEST,
        os_name="Windows",
        os_version="11",
        architecture="AMD64",
        winget_available=True,
        captured_at=NOW,
    )

    payload = heartbeat.as_payload()

    assert payload["status"] == "online"
    assert set(payload) == {
        "device_id",
        "organization_id",
        "sequence",
        "status",
        "agent_version",
        "inventory_fingerprint",
        "os_name",
        "os_version",
        "architecture",
        "winget_available",
        "captured_at",
    }
