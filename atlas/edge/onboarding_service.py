"""End-to-end governed employee onboarding orchestration for Atlas Edge."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable

from atlas.edge.audit import EdgeAuditOutcome
from atlas.edge.governance import EdgeAction, EdgePrincipal
from atlas.edge.governed_service import GovernedEdgeService
from atlas.edge.onboarding import (
    EmployeeOnboarding,
    EmployeeOnboardingReport,
    EmployeeOnboardingStatus,
)
from atlas.edge.onboarding_store import EmployeeOnboardingStore
from atlas.edge.profiles import (
    EdgeConfigurationPreview,
    hash_private_reference,
)
from atlas.edge.task_queue import EdgeTaskStatus


@dataclass(frozen=True, slots=True)
class EmployeeOnboardingStart:
    onboarding: EmployeeOnboarding
    preview: EdgeConfigurationPreview


class EmployeeOnboardingError(ValueError):
    """Safe workflow failure without private employee data."""


class EmployeeOnboardingService:
    """Coordinates the reviewed Edge flow without persisting approval tokens."""

    def __init__(
        self,
        *,
        governed: GovernedEdgeService,
        store: EmployeeOnboardingStore,
        max_active: int = 20,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_active <= 0:
            raise ValueError("O limite de onboardings ativos deve ser positivo.")
        self._governed = governed
        self._store = store
        self._max_active = max_active
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._pending_tokens: dict[str, str] = {}
        self._authorizations: dict[str, str] = {}

    def start(
        self,
        principal: EdgePrincipal,
        profile_id: str,
        *,
        employee_reference: str,
    ) -> EmployeeOnboardingStart:
        employee_hash = hash_private_reference(
            employee_reference,
            "A referência do funcionário",
        )
        self._ensure_capacity(principal.organization_id, employee_hash)
        challenge = self._governed.prepare_configuration(
            principal,
            profile_id,
            employee_reference=employee_reference,
        )
        preview = challenge.preview
        record = EmployeeOnboarding(
            organization_id=preview.organization_id,
            device_id=preview.device_id,
            employee_reference_hash=preview.employee_reference_hash,
            requester_hash=preview.requester_hash,
            profile_id=preview.plan.profile_id,
            status=EmployeeOnboardingStatus.AWAITING_APPROVAL,
            created_at=self._now(),
            updated_at=self._now(),
            plan_request_id=preview.request_id,
            plan_digest=preview.plan.digest(),
        )
        try:
            self._store.save(record)
        except Exception:
            self._governed.discard_pending_plan(challenge.token)
            raise
        self._pending_tokens[record.onboarding_id] = challenge.token
        return EmployeeOnboardingStart(record, preview)

    def approve(
        self,
        principal: EdgePrincipal,
        onboarding_id: str,
    ) -> EmployeeOnboarding:
        record = self._require_owned(principal, onboarding_id)
        self._require_status(
            record,
            {EmployeeOnboardingStatus.AWAITING_APPROVAL},
        )
        token = self._pending_tokens.get(onboarding_id)
        if token is None:
            self._mark_action_required(record, "approval_session_lost")
            raise EmployeeOnboardingError(
                "A sessão de aprovação foi perdida; gere outro plano."
            )
        authorization = self._governed.authorize_configuration(
            principal,
            token,
        )
        updated = self._transition(
            record,
            EmployeeOnboardingStatus.AUTHORIZED,
            error_code=None,
        )
        try:
            self._store.save(updated)
        except Exception:
            self._governed.discard_authorization(
                authorization.authorization_id
            )
            raise
        self._pending_tokens.pop(onboarding_id, None)
        self._authorizations[onboarding_id] = authorization.authorization_id
        return updated

    def enqueue(
        self,
        principal: EdgePrincipal,
        onboarding_id: str,
    ) -> EmployeeOnboarding:
        record = self._require_owned(principal, onboarding_id)
        self._require_status(record, {EmployeeOnboardingStatus.AUTHORIZED})
        authorization_id = self._authorizations.get(onboarding_id)
        if authorization_id is None:
            self._mark_action_required(record, "authorization_session_lost")
            raise EmployeeOnboardingError(
                "A autorização transitória foi perdida; gere outro plano."
            )
        task = self._governed.enqueue_authorization(
            principal,
            authorization_id,
        )
        updated = self._transition(
            record,
            EmployeeOnboardingStatus.QUEUED,
            task_id=task.task_id,
            error_code=None,
        )
        try:
            self._store.save(updated)
        except Exception:
            self._governed.cancel_task(principal, task.task_id)
            raise
        self._authorizations.pop(onboarding_id, None)
        return updated

    def execute(
        self,
        principal: EdgePrincipal,
        onboarding_id: str,
    ) -> EmployeeOnboarding:
        record = self._require_owned(principal, onboarding_id)
        self._require_status(record, {EmployeeOnboardingStatus.QUEUED})
        if record.task_id is None:
            raise EmployeeOnboardingError("O onboarding não possui tarefa.")
        running = self._transition(
            record,
            EmployeeOnboardingStatus.RUNNING,
            error_code=None,
        )
        self._store.save(running)
        try:
            result = self._governed.execute_task(principal, record.task_id)
        except Exception:
            recovered = self._status_after_execution_error(running, principal)
            self._store.save(recovered)
            raise
        status = _onboarding_status(result.task.status)
        updated = self._transition(
            running,
            status,
            evidence_id=result.evidence.evidence_id,
            result_status=result.evidence.status.value,
            error_code=result.task.error_code,
        )
        self._store.save(updated)
        return updated

    def cancel(
        self,
        principal: EdgePrincipal,
        onboarding_id: str,
    ) -> EmployeeOnboarding:
        self._governed.authorize_onboarding_action(
            principal,
            EdgeAction.ONBOARDING_CANCEL,
            onboarding_id=onboarding_id,
        )
        try:
            record = self._require_owned(principal, onboarding_id)
            if record.terminal:
                raise EmployeeOnboardingError("O onboarding já foi encerrado.")
            if record.status is EmployeeOnboardingStatus.RUNNING:
                raise EmployeeOnboardingError(
                    "Uma execução em andamento não pode ser cancelada."
                )
            if record.status is EmployeeOnboardingStatus.QUEUED:
                if record.task_id is None:
                    raise EmployeeOnboardingError(
                        "O onboarding não possui tarefa para cancelar."
                    )
                self._governed.cancel_task(principal, record.task_id)
            token = self._pending_tokens.pop(onboarding_id, None)
            if token is not None:
                self._governed.discard_pending_plan(token)
            authorization_id = self._authorizations.pop(onboarding_id, None)
            if authorization_id is not None:
                self._governed.discard_authorization(authorization_id)
            updated = self._transition(
                record,
                EmployeeOnboardingStatus.CANCELLED,
                error_code="cancelled_by_operator",
            )
            self._store.save(updated)
        except Exception:
            self._governed.record_onboarding_outcome(
                principal,
                EdgeAction.ONBOARDING_CANCEL,
                EdgeAuditOutcome.FAILED,
                "onboarding_cancel_failed",
                onboarding_id=onboarding_id,
            )
            raise
        self._governed.record_onboarding_outcome(
            principal,
            EdgeAction.ONBOARDING_CANCEL,
            EdgeAuditOutcome.SUCCEEDED,
            "onboarding_cancelled",
            onboarding_id=onboarding_id,
        )
        return updated

    def restart_plan(
        self,
        principal: EdgePrincipal,
        onboarding_id: str,
        *,
        employee_reference: str,
    ) -> EmployeeOnboardingStart:
        record = self._require_owned(principal, onboarding_id)
        self._require_status(record, {EmployeeOnboardingStatus.ACTION_REQUIRED})
        employee_hash = hash_private_reference(
            employee_reference,
            "A referência do funcionário",
        )
        if employee_hash != record.employee_reference_hash:
            raise PermissionError("A referência não pertence ao onboarding.")
        challenge = self._governed.prepare_configuration(
            principal,
            record.profile_id,
            employee_reference=employee_reference,
        )
        updated = self._transition(
            record,
            EmployeeOnboardingStatus.AWAITING_APPROVAL,
            requester_hash=challenge.preview.requester_hash,
            plan_request_id=challenge.preview.request_id,
            plan_digest=challenge.preview.plan.digest(),
            task_id=None,
            evidence_id=None,
            result_status=None,
            error_code=None,
        )
        try:
            self._store.save(updated)
        except Exception:
            self._governed.discard_pending_plan(challenge.token)
            raise
        self._pending_tokens[onboarding_id] = challenge.token
        return EmployeeOnboardingStart(updated, challenge.preview)

    def list(
        self,
        principal: EdgePrincipal,
    ) -> tuple[EmployeeOnboarding, ...]:
        self._governed.authorize_onboarding_action(
            principal,
            EdgeAction.ONBOARDING_LIST,
        )
        records = tuple(
            record
            for record in self._store.list()
            if record.organization_id == principal.organization_id
        )
        self._governed.record_onboarding_outcome(
            principal,
            EdgeAction.ONBOARDING_LIST,
            EdgeAuditOutcome.SUCCEEDED,
            "onboardings_listed",
        )
        return records

    def get(
        self,
        principal: EdgePrincipal,
        onboarding_id: str,
    ) -> EmployeeOnboarding:
        self._governed.authorize_onboarding_action(
            principal,
            EdgeAction.ONBOARDING_LIST,
            onboarding_id=onboarding_id,
        )
        try:
            record = self._require_owned(principal, onboarding_id)
        except Exception:
            self._governed.record_onboarding_outcome(
                principal,
                EdgeAction.ONBOARDING_LIST,
                EdgeAuditOutcome.FAILED,
                "onboarding_read_failed",
                onboarding_id=onboarding_id,
            )
            raise
        self._governed.record_onboarding_outcome(
            principal,
            EdgeAction.ONBOARDING_LIST,
            EdgeAuditOutcome.SUCCEEDED,
            "onboarding_read",
            onboarding_id=onboarding_id,
        )
        return record

    def report(
        self,
        principal: EdgePrincipal,
    ) -> EmployeeOnboardingReport:
        records = self.list(principal)
        return EmployeeOnboardingReport(
            organization_id=principal.organization_id,
            total=len(records),
            active=sum(
                not record.terminal
                and record.status is not EmployeeOnboardingStatus.ACTION_REQUIRED
                for record in records
            ),
            action_required=sum(
                record.status is EmployeeOnboardingStatus.ACTION_REQUIRED
                for record in records
            ),
            simulated=sum(
                record.status is EmployeeOnboardingStatus.SIMULATED
                for record in records
            ),
            succeeded=sum(
                record.status is EmployeeOnboardingStatus.SUCCEEDED
                for record in records
            ),
            failed=sum(
                record.status is EmployeeOnboardingStatus.FAILED
                for record in records
            ),
            cancelled=sum(
                record.status is EmployeeOnboardingStatus.CANCELLED
                for record in records
            ),
            generated_at=self._now(),
        )

    def reconcile(
        self,
        principal: EdgePrincipal,
    ) -> tuple[EmployeeOnboarding, ...]:
        self._governed.authorize_onboarding_action(
            principal,
            EdgeAction.ONBOARDING_RECONCILE,
        )
        try:
            tasks = {
                task.task_id: task
                for task in self._governed.list_tasks(principal)
            }
            results: list[EmployeeOnboarding] = []
            for record in self._store.list():
                if record.organization_id != principal.organization_id:
                    continue
                updated = self._reconcile_record(record, tasks)
                if updated != record:
                    self._store.save(updated)
                results.append(updated)
        except Exception:
            self._governed.record_onboarding_outcome(
                principal,
                EdgeAction.ONBOARDING_RECONCILE,
                EdgeAuditOutcome.FAILED,
                "onboarding_reconcile_failed",
            )
            raise
        self._governed.record_onboarding_outcome(
            principal,
            EdgeAction.ONBOARDING_RECONCILE,
            EdgeAuditOutcome.SUCCEEDED,
            "onboardings_reconciled",
        )
        return tuple(results)

    def _reconcile_record(self, record, tasks):
        if record.terminal:
            return record
        if record.task_id is not None:
            task = tasks.get(record.task_id)
            if task is None:
                return self._transition(
                    record,
                    EmployeeOnboardingStatus.ACTION_REQUIRED,
                    error_code="task_not_found",
                )
            return self._sync_task(record, task)
        if (
            record.onboarding_id not in self._pending_tokens
            and record.onboarding_id not in self._authorizations
            and record.status
            in {
                EmployeeOnboardingStatus.PLANNING,
                EmployeeOnboardingStatus.AWAITING_APPROVAL,
                EmployeeOnboardingStatus.AUTHORIZED,
            }
        ):
            return self._transition(
                record,
                EmployeeOnboardingStatus.ACTION_REQUIRED,
                error_code="approval_session_lost",
            )
        return record

    def _status_after_execution_error(self, record, principal):
        tasks = {
            task.task_id: task for task in self._governed.list_tasks(principal)
        }
        task = tasks.get(record.task_id)
        if task is None:
            return self._transition(
                record,
                EmployeeOnboardingStatus.ACTION_REQUIRED,
                error_code="task_not_found",
            )
        return self._sync_task(record, task)

    def _sync_task(self, record, task):
        status = _onboarding_status(task.status)
        if (
            record.status is status
            and record.evidence_id == task.evidence_id
            and record.result_status == task.result_status
            and record.error_code == task.error_code
        ):
            return record
        return self._transition(
            record,
            status,
            evidence_id=task.evidence_id,
            result_status=task.result_status,
            error_code=task.error_code,
        )

    def _mark_action_required(
        self,
        record: EmployeeOnboarding,
        error_code: str,
    ) -> EmployeeOnboarding:
        updated = self._transition(
            record,
            EmployeeOnboardingStatus.ACTION_REQUIRED,
            error_code=error_code,
        )
        self._store.save(updated)
        return updated

    def _ensure_capacity(self, organization_id: str, employee_hash: str) -> None:
        active = tuple(
            item
            for item in self._store.list()
            if item.organization_id == organization_id and not item.terminal
        )
        if len(active) >= self._max_active:
            raise OverflowError("Existem muitos onboardings ativos.")
        if any(
            item.employee_reference_hash == employee_hash for item in active
        ):
            raise EmployeeOnboardingError(
                "Já existe onboarding ativo para essa referência."
            )

    def _require_owned(
        self,
        principal: EdgePrincipal,
        onboarding_id: str,
    ) -> EmployeeOnboarding:
        record = self._store.get(onboarding_id)
        if record is None:
            raise EmployeeOnboardingError("O onboarding não foi encontrado.")
        if record.organization_id != principal.organization_id:
            raise PermissionError("O onboarding pertence a outra organização.")
        if record.device_id != self._governed.device_id:
            raise PermissionError("O onboarding pertence a outro dispositivo.")
        return record

    @staticmethod
    def _require_status(record, allowed) -> None:
        if record.status not in allowed:
            raise EmployeeOnboardingError(
                "O onboarding não está disponível para essa operação."
            )

    def _transition(
        self,
        record: EmployeeOnboarding,
        status: EmployeeOnboardingStatus,
        **changes,
    ) -> EmployeeOnboarding:
        if status is not record.status and status not in _TRANSITIONS[record.status]:
            raise EmployeeOnboardingError("A transição do onboarding é inválida.")
        return replace(
            record,
            status=status,
            updated_at=self._now(),
            revision=record.revision + 1,
            **changes,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("O relógio do onboarding deve possuir fuso horário.")
        return value.astimezone(timezone.utc)


_TRANSITIONS = {
    EmployeeOnboardingStatus.PLANNING: {
        EmployeeOnboardingStatus.AWAITING_APPROVAL,
        EmployeeOnboardingStatus.ACTION_REQUIRED,
        EmployeeOnboardingStatus.FAILED,
        EmployeeOnboardingStatus.CANCELLED,
    },
    EmployeeOnboardingStatus.AWAITING_APPROVAL: {
        EmployeeOnboardingStatus.AUTHORIZED,
        EmployeeOnboardingStatus.ACTION_REQUIRED,
        EmployeeOnboardingStatus.FAILED,
        EmployeeOnboardingStatus.CANCELLED,
    },
    EmployeeOnboardingStatus.AUTHORIZED: {
        EmployeeOnboardingStatus.QUEUED,
        EmployeeOnboardingStatus.ACTION_REQUIRED,
        EmployeeOnboardingStatus.FAILED,
        EmployeeOnboardingStatus.CANCELLED,
    },
    EmployeeOnboardingStatus.QUEUED: {
        EmployeeOnboardingStatus.RUNNING,
        EmployeeOnboardingStatus.ACTION_REQUIRED,
        EmployeeOnboardingStatus.SIMULATED,
        EmployeeOnboardingStatus.SUCCEEDED,
        EmployeeOnboardingStatus.FAILED,
        EmployeeOnboardingStatus.CANCELLED,
    },
    EmployeeOnboardingStatus.RUNNING: {
        EmployeeOnboardingStatus.QUEUED,
        EmployeeOnboardingStatus.ACTION_REQUIRED,
        EmployeeOnboardingStatus.SIMULATED,
        EmployeeOnboardingStatus.SUCCEEDED,
        EmployeeOnboardingStatus.FAILED,
        EmployeeOnboardingStatus.CANCELLED,
    },
    EmployeeOnboardingStatus.ACTION_REQUIRED: {
        EmployeeOnboardingStatus.AWAITING_APPROVAL,
        EmployeeOnboardingStatus.FAILED,
        EmployeeOnboardingStatus.CANCELLED,
    },
    EmployeeOnboardingStatus.SIMULATED: set(),
    EmployeeOnboardingStatus.SUCCEEDED: set(),
    EmployeeOnboardingStatus.FAILED: set(),
    EmployeeOnboardingStatus.CANCELLED: set(),
}


def _onboarding_status(status: EdgeTaskStatus) -> EmployeeOnboardingStatus:
    return {
        EdgeTaskStatus.QUEUED: EmployeeOnboardingStatus.QUEUED,
        EdgeTaskStatus.RUNNING: EmployeeOnboardingStatus.RUNNING,
        EdgeTaskStatus.SIMULATED: EmployeeOnboardingStatus.SIMULATED,
        EdgeTaskStatus.SUCCEEDED: EmployeeOnboardingStatus.SUCCEEDED,
        EdgeTaskStatus.FAILED: EmployeeOnboardingStatus.FAILED,
        EdgeTaskStatus.CANCELLED: EmployeeOnboardingStatus.CANCELLED,
        EdgeTaskStatus.EXPIRED: EmployeeOnboardingStatus.FAILED,
    }[status]
