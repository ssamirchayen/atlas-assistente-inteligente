"""Política de recuperação bounded do Atlas Vision Etapa 15."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    retry_allowed: bool
    rollback_allowed: bool
    reason_code: str


def decide_recovery(
    *,
    action_performed: bool,
    verified: bool,
    reversible: bool,
    attempts: int,
) -> RecoveryDecision:
    """Impede repetição de ação enviada e limita retry pré-ação a uma vez."""

    if verified:
        return RecoveryDecision(False, False, "recovery_not_needed")

    if action_performed:
        return RecoveryDecision(
            retry_allowed=False,
            rollback_allowed=reversible,
            reason_code=(
                "rollback_reversible_action"
                if reversible
                else "action_sent_no_retry"
            ),
        )

    if attempts < 1:
        return RecoveryDecision(True, False, "single_safe_retry")

    return RecoveryDecision(False, False, "retry_budget_exhausted")

