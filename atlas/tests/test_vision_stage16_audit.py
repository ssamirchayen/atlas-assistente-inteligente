import json
from datetime import datetime, timezone

from atlas.vision.audit import VisionAuditTrail


def test_audit_persists_only_redacted_operational_metadata(tmp_path) -> None:
    path = tmp_path / "vision-audit.jsonl"
    trail = VisionAuditTrail(
        path,
        clock=lambda: datetime(2026, 8, 30, tzinfo=timezone.utc),
    )

    event = trail.record(
        operation="control_state",
        success=True,
        reason_code="control_checked_confirmed",
        action_count=1,
        duration_ms=12,
        context_token="dom:private-page-identity",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert event.context_kind == "dom"
    assert payload["context_kind"] == "dom"
    assert "private-page-identity" not in path.read_text(encoding="utf-8")
    assert set(payload) == {
        "timestamp",
        "operation",
        "outcome",
        "reason_code",
        "action_count",
        "duration_ms",
        "context_kind",
    }


def test_audit_snapshot_is_immutable_tuple() -> None:
    trail = VisionAuditTrail()
    trail.record(
        operation="final_action_prepare",
        success=True,
        reason_code="vision_final_confirmation_required",
        action_count=0,
        duration_ms=1,
    )

    snapshot = trail.snapshot()

    assert isinstance(snapshot, tuple)
    assert len(snapshot) == 1
    assert snapshot[0].operation == "final_action_prepare"

