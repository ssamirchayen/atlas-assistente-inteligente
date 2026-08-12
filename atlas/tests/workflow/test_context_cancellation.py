from __future__ import annotations

from datetime import timezone

import pytest

from atlas.workflow.cancellation import (
    CancellationSnapshot,
    CancellationToken,
    WorkflowCancelledError,
)
from atlas.workflow.context import WorkflowContext


def test_context_starts_with_cancellation_token() -> None:
    context = WorkflowContext()

    assert isinstance(context.cancellation, CancellationToken)
    assert context.is_cancelled() is False


def test_cancel_marks_context_as_cancelled() -> None:
    context = WorkflowContext()

    changed = context.cancel(
        reason="Solicitado pelo usuário",
        requested_by="Ssamir",
    )

    assert changed is True
    assert context.is_cancelled() is True

    snapshot = context.cancellation_snapshot()

    assert isinstance(snapshot, CancellationSnapshot)
    assert snapshot.cancelled is True
    assert snapshot.reason == "Solicitado pelo usuário"
    assert snapshot.requested_by == "Ssamir"
    assert snapshot.cancelled_at is not None
    assert snapshot.cancelled_at.tzinfo == timezone.utc


def test_cancel_records_audit_history() -> None:
    context = WorkflowContext()

    context.cancel(
        reason="Interrupção manual",
        requested_by="Administrador",
    )

    assert len(context.history) == 1

    event = context.history[0]

    assert event["event"] == "workflow_cancellation_requested"
    assert event["reason"] == "Interrupção manual"
    assert event["requested_by"] == "Administrador"
    assert isinstance(event["cancelled_at"], str)


def test_duplicate_cancel_does_not_duplicate_history() -> None:
    context = WorkflowContext()

    first_changed = context.cancel(
        reason="Primeiro motivo",
        requested_by="Usuário A",
    )
    second_changed = context.cancel(
        reason="Segundo motivo",
        requested_by="Usuário B",
    )

    assert first_changed is True
    assert second_changed is False
    assert len(context.history) == 1

    snapshot = context.cancellation_snapshot()

    assert snapshot.reason == "Primeiro motivo"
    assert snapshot.requested_by == "Usuário A"


def test_throw_if_cancelled_does_nothing_before_cancellation() -> None:
    context = WorkflowContext()

    context.throw_if_cancelled()


def test_throw_if_cancelled_raises_domain_error() -> None:
    context = WorkflowContext()
    context.cancel(
        reason="Parada de emergência",
        requested_by="Operador",
    )

    with pytest.raises(WorkflowCancelledError) as exc_info:
        context.throw_if_cancelled()

    error = exc_info.value

    assert error.reason == "Parada de emergência"
    assert error.requested_by == "Operador"


def test_clear_preserves_cancellation_state() -> None:
    context = WorkflowContext()

    context.set("cliente", "Empresa Atlas")
    context.set_result("resultado")
    context.add_history("custom_event")
    context.cancel(
        reason="Cancelamento persistente",
        requested_by="Sistema",
    )

    context.clear()

    assert context.data == {}
    assert context.results == []
    assert context.history == []
    assert context.is_cancelled() is True

    snapshot = context.cancellation_snapshot()

    assert snapshot.reason == "Cancelamento persistente"
    assert snapshot.requested_by == "Sistema"


def test_existing_context_api_remains_compatible() -> None:
    context = WorkflowContext()

    context.set("cliente", "Empresa X")
    context.update({"setor": "Financeiro"})
    context.set_result("resultado-1")
    context.add_history(
        "step_completed",
        action="abrir_relatorio",
    )

    assert context.get("cliente") == "Empresa X"
    assert context.get("setor") == "Financeiro"
    assert context.exists("cliente") is True
    assert context.last_result() == "resultado-1"
    assert context.as_dict() == {
        "cliente": "Empresa X",
        "setor": "Financeiro",
    }

    context.remove("cliente")

    assert context.exists("cliente") is False
