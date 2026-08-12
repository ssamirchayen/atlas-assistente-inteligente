from __future__ import annotations

from datetime import timezone

import pytest

from atlas.workflow.cancellation import (
    CancellationSnapshot,
    CancellationToken,
    WorkflowCancelledError,
)


def test_token_starts_not_cancelled() -> None:
    token = CancellationToken()

    assert token.is_cancelled() is False
    assert token.reason is None
    assert token.requested_by is None
    assert token.cancelled_at is None


def test_cancel_marks_token_and_stores_audit_data() -> None:
    token = CancellationToken()

    changed = token.cancel(
        reason="Solicitado pelo operador",
        requested_by="Ssamir",
    )

    assert changed is True
    assert token.is_cancelled() is True
    assert token.reason == "Solicitado pelo operador"
    assert token.requested_by == "Ssamir"
    assert token.cancelled_at is not None
    assert token.cancelled_at.tzinfo == timezone.utc


def test_cancel_is_idempotent_and_preserves_first_request() -> None:
    token = CancellationToken()

    first_changed = token.cancel(
        reason="Primeiro motivo",
        requested_by="Primeiro usuário",
    )
    first_snapshot = token.snapshot()

    second_changed = token.cancel(
        reason="Segundo motivo",
        requested_by="Segundo usuário",
    )
    second_snapshot = token.snapshot()

    assert first_changed is True
    assert second_changed is False
    assert second_snapshot == first_snapshot


def test_cancel_normalizes_blank_audit_fields() -> None:
    token = CancellationToken()

    token.cancel(
        reason="   ",
        requested_by="   ",
    )

    assert token.reason is None
    assert token.requested_by is None


def test_throw_if_cancelled_does_nothing_before_cancellation() -> None:
    token = CancellationToken()

    token.throw_if_cancelled()


def test_throw_if_cancelled_raises_domain_error() -> None:
    token = CancellationToken()
    token.cancel(
        reason="Interrupção de emergência",
        requested_by="Administrador",
    )

    with pytest.raises(WorkflowCancelledError) as exc_info:
        token.throw_if_cancelled()

    error = exc_info.value

    assert error.reason == "Interrupção de emergência"
    assert error.requested_by == "Administrador"
    assert "Interrupção de emergência" in str(error)
    assert "Administrador" in str(error)


def test_wait_returns_false_when_timeout_expires() -> None:
    token = CancellationToken()

    assert token.wait(timeout=0.001) is False


def test_wait_returns_true_after_cancellation() -> None:
    token = CancellationToken()
    token.cancel()

    assert token.wait(timeout=0.001) is True


def test_wait_rejects_negative_timeout() -> None:
    token = CancellationToken()

    with pytest.raises(
        ValueError,
        match="não pode ser negativo",
    ):
        token.wait(timeout=-1)


def test_snapshot_is_immutable_and_serializable() -> None:
    token = CancellationToken()
    token.cancel(
        reason="Manutenção",
        requested_by="Sistema",
    )

    snapshot = token.snapshot()

    assert isinstance(snapshot, CancellationSnapshot)
    assert snapshot.cancelled is True

    serialized = snapshot.as_dict()

    assert serialized["cancelled"] is True
    assert serialized["reason"] == "Manutenção"
    assert serialized["requested_by"] == "Sistema"
    assert isinstance(serialized["cancelled_at"], str)
