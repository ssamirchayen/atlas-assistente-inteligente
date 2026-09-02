import json
from datetime import datetime, timezone

import pytest

from atlas.edge import (
    DeviceIdentity,
    EdgePersistentState,
    EdgeStateError,
    EdgeStateStore,
)


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def _state() -> EdgePersistentState:
    return EdgePersistentState(
        identity=DeviceIdentity(
            device_id=f"edge_{'2' * 32}",
            created_at=NOW,
        )
    )


def test_store_round_trip_is_atomic_and_bounded(tmp_path) -> None:
    path = tmp_path / "edge" / "device.json"
    store = EdgeStateStore(path)

    store.save(_state())

    assert store.load() == _state()
    assert path.stat().st_size < 64 * 1024
    assert list(path.parent.glob("*.tmp")) == []


def test_store_fails_closed_on_corrupt_state(tmp_path) -> None:
    path = tmp_path / "device.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(EdgeStateError, match="integridade"):
        EdgeStateStore(path).load()

    assert path.read_text(encoding="utf-8") == "{invalid"


def test_store_rejects_oversized_state_before_parsing(tmp_path) -> None:
    path = tmp_path / "device.json"
    path.write_text(json.dumps({"padding": "x" * 100}), encoding="utf-8")

    with pytest.raises(EdgeStateError, match="excedeu"):
        EdgeStateStore(path, max_bytes=32).load()
