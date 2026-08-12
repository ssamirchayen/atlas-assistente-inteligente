from __future__ import annotations

from datetime import timezone
from unittest.mock import Mock

import pytest

from atlas.workflow.cancellation import WorkflowCancelledError
from atlas.workflow.context import WorkflowContext
from atlas.workflow.state import WorkflowState
from atlas.workflow.step import WorkflowStep


def make_step(action: str) -> WorkflowStep:
    step = Mock(spec=WorkflowStep)
    step.action = action
    return step


def test_state_starts_not_cancelled() -> None:
    state = WorkflowState(steps=[])

    assert state.cancelled is False
    assert state.cancellation_reason is None
    assert state.cancellation_requested_by is None
    assert state.cancelled_at is None
    assert state.cancelled_step is None
    assert state.cancelled_index is None


def test_cancel_marks_state_as_finished() -> None:
    step = make_step("abrir_relatorio")
    state = WorkflowState(steps=[step])
    state.next_step()

    changed = state.cancel(
        reason="Solicitado pelo usuário",
        requested_by="Ssamir",
    )

    assert changed is True
    assert state.cancelled is True
    assert state.finished is True
    assert state.failed is False
    assert state.error is None
    assert state.cancelled_step is step
    assert state.cancelled_index == 0


def test_cancel_exposes_audit_information() -> None:
    state = WorkflowState(steps=[])

    state.cancel(
        reason="Parada administrativa",
        requested_by="Administrador",
    )

    assert state.cancellation_reason == "Parada administrativa"
    assert state.cancellation_requested_by == "Administrador"
    assert state.cancelled_at is not None
    assert state.cancelled_at.tzinfo == timezone.utc


def test_cancel_is_idempotent() -> None:
    state = WorkflowState(steps=[])

    first_changed = state.cancel(
        reason="Primeiro motivo",
        requested_by="Usuário A",
    )
    second_changed = state.cancel(
        reason="Segundo motivo",
        requested_by="Usuário B",
    )

    assert first_changed is True
    assert second_changed is False
    assert state.cancellation_reason == "Primeiro motivo"
    assert state.cancellation_requested_by == "Usuário A"


def test_has_next_detects_context_cancellation() -> None:
    context = WorkflowContext()
    step = make_step("enviar_email")
    state = WorkflowState(
        steps=[step],
        context=context,
    )

    context.cancel(
        reason="Cancelamento externo",
        requested_by="API",
    )

    assert state.has_next is False
    assert state.cancelled is True
    assert state.finished is True
    assert state.cancelled_index == 0


def test_next_step_returns_none_after_cancellation() -> None:
    step = make_step("gerar_relatorio")
    state = WorkflowState(steps=[step])

    state.cancel(
        reason="Operação interrompida",
        requested_by="Operador",
    )

    assert state.next_step() is None
    assert state.current_step is None


def test_completed_step_is_not_recorded_after_cancellation() -> None:
    step = make_step("processar_dados")
    state = WorkflowState(steps=[step])
    state.next_step()

    state.cancel(
        reason="Interrupção",
        requested_by="Sistema",
    )
    state.mark_completed()

    assert state.completed_steps == []
    assert state.current_index == 0
    assert state.cancelled_step is step


def test_failure_does_not_override_cancellation() -> None:
    step = make_step("ação_crítica")
    state = WorkflowState(steps=[step])
    state.next_step()

    state.cancel(
        reason="Cancelado antes da falha",
        requested_by="Usuário",
    )
    state.mark_failed("Erro posterior")

    assert state.cancelled is True
    assert state.failed is False
    assert state.error is None
    assert state.failed_steps == []


def test_throw_if_cancelled_delegates_to_context() -> None:
    state = WorkflowState(steps=[])

    state.cancel(
        reason="Parada de emergência",
        requested_by="Operador",
    )

    with pytest.raises(WorkflowCancelledError):
        state.throw_if_cancelled()


def test_reset_clears_cancellation_and_execution_state() -> None:
    step = make_step("abrir_sistema")
    state = WorkflowState(steps=[step])
    state.next_step()
    state.cancel(
        reason="Primeira execução cancelada",
        requested_by="Usuário",
    )

    state.reset()

    assert state.cancelled is False
    assert state.finished is False
    assert state.failed is False
    assert state.error is None
    assert state.current_index == 0
    assert state.current_step is None
    assert state.cancelled_step is None
    assert state.cancelled_index is None
    assert state.has_next is True


def test_existing_state_flow_remains_compatible() -> None:
    first_step = make_step("primeira_ação")
    second_step = make_step("segunda_ação")
    state = WorkflowState(
        steps=[first_step, second_step]
    )

    assert state.next_step() is first_step
    state.mark_completed()

    assert state.current_index == 1
    assert state.completed_steps == [first_step]
    assert state.finished is False

    assert state.next_step() is second_step
    state.mark_skipped()

    assert state.current_index == 2
    assert state.skipped_steps == [second_step]
    assert state.finished is True
    assert state.progress == 1.0
