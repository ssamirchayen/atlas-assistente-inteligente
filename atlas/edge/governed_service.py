"""Governed facade over Atlas Edge planning and execution services."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from atlas.edge.agent import ITProvisioningAgent
from atlas.edge.audit import (
    EdgeAuditEvent,
    EdgeAuditOutcome,
    EdgeAuditTrail,
    build_edge_audit_event,
)
from atlas.edge.execution import EdgeExecutionResult, EdgeExecutionService
from atlas.edge.governance import (
    EdgeAction,
    EdgePolicyDenied,
    EdgePolicyEngine,
    EdgePrincipal,
)
from atlas.edge.profile_service import EdgeProfileService
from atlas.edge.profiles import (
    AuthorizedEdgePlan,
    EdgePlanChallenge,
    EmployeeProfileSummary,
)
from atlas.edge.task_queue import EdgeExecutionTask


class GovernedEdgeService:
    """Single entry point enforcing policy and recording every state change."""

    def __init__(
        self,
        *,
        agent: ITProvisioningAgent,
        profile_service: EdgeProfileService,
        execution_service: EdgeExecutionService,
        policy: EdgePolicyEngine,
        audit: EdgeAuditTrail,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._agent = agent
        self._profiles = profile_service
        self._execution = execution_service
        self._policy = policy
        self._audit = audit
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def organization_id(self) -> str:
        return self._organization_id()

    @property
    def device_id(self) -> str:
        return self._agent.state.identity.device_id

    @property
    def dry_run(self) -> bool:
        return self._execution.dry_run

    def list_profiles(
        self,
        principal: EdgePrincipal,
    ) -> tuple[EmployeeProfileSummary, ...]:
        organization_id = self._organization_id()
        self._authorize(
            EdgeAction.PROFILES_LIST,
            principal,
            organization_id=organization_id,
        )
        result = self._profiles.list_profiles()
        self._record(
            principal,
            EdgeAction.PROFILES_LIST,
            EdgeAuditOutcome.SUCCEEDED,
            "profiles_listed",
        )
        return result

    def prepare_configuration(
        self,
        principal: EdgePrincipal,
        profile_id: str,
        *,
        employee_reference: str,
    ) -> EdgePlanChallenge:
        organization_id = self._organization_id()
        self._authorize(
            EdgeAction.PLAN_PREPARE,
            principal,
            organization_id=organization_id,
            profile_id=profile_id,
        )
        challenge = None
        try:
            challenge = self._profiles.prepare_configuration(
                profile_id,
                employee_reference=employee_reference,
                requester_id=principal.principal_id,
            )
            self._policy.require(
                EdgeAction.PLAN_PREPARE,
                principal,
                target_organization_id=organization_id,
                profile_id=profile_id,
                plan=challenge.preview.plan,
            )
        except Exception as exc:
            if challenge is not None:
                self._profiles.revoke_pending_configuration(challenge.token)
            self._record_failure(principal, EdgeAction.PLAN_PREPARE, exc)
            raise
        self._record(
            principal,
            EdgeAction.PLAN_PREPARE,
            EdgeAuditOutcome.SUCCEEDED,
            "plan_prepared",
            target_id=challenge.preview.request_id,
            plan_digest=challenge.preview.plan.digest(),
        )
        return challenge

    def authorize_configuration(
        self,
        principal: EdgePrincipal,
        token: str,
    ) -> AuthorizedEdgePlan:
        organization_id = self._organization_id()
        pending = self._profiles.inspect_pending_configuration(token)
        self._authorize(
            EdgeAction.PLAN_APPROVE,
            principal,
            organization_id=organization_id,
            profile_id=pending.preview.plan.profile_id,
            plan=pending.preview.plan,
            target_id=pending.preview.request_id,
        )
        try:
            authorization = self._profiles.authorize_configuration(
                token,
                approver_id=principal.principal_id,
            )
        except Exception as exc:
            self._record_failure(
                principal,
                EdgeAction.PLAN_APPROVE,
                exc,
                target_id=pending.preview.request_id,
            )
            raise
        self._record(
            principal,
            EdgeAction.PLAN_APPROVE,
            EdgeAuditOutcome.SUCCEEDED,
            "plan_approved",
            target_id=authorization.preview.request_id,
            plan_digest=authorization.preview.plan.digest(),
        )
        return authorization

    def enqueue_authorization(
        self,
        principal: EdgePrincipal,
        authorization_id: str,
    ) -> EdgeExecutionTask:
        organization_id = self._organization_id()
        authorization = self._profiles.inspect_authorized_configuration(
            authorization_id
        )
        self._authorize(
            EdgeAction.TASK_ENQUEUE,
            principal,
            organization_id=organization_id,
            profile_id=authorization.preview.plan.profile_id,
            plan=authorization.preview.plan,
            target_id=authorization.preview.request_id,
        )
        try:
            task = self._execution.enqueue_authorization(authorization_id)
        except Exception as exc:
            self._record_failure(principal, EdgeAction.TASK_ENQUEUE, exc)
            raise
        self._record(
            principal,
            EdgeAction.TASK_ENQUEUE,
            EdgeAuditOutcome.SUCCEEDED,
            "task_enqueued",
            target_id=task.task_id,
            plan_digest=task.plan.digest(),
            dry_run=self._execution.dry_run,
        )
        return task

    def list_tasks(
        self,
        principal: EdgePrincipal,
    ) -> tuple[EdgeExecutionTask, ...]:
        organization_id = self._organization_id()
        self._authorize(
            EdgeAction.TASK_LIST,
            principal,
            organization_id=organization_id,
        )
        tasks = tuple(
            task
            for task in self._execution.list_tasks()
            if task.organization_id == principal.organization_id
        )
        self._record(
            principal,
            EdgeAction.TASK_LIST,
            EdgeAuditOutcome.SUCCEEDED,
            "tasks_listed",
        )
        return tasks

    def execute_task(
        self,
        principal: EdgePrincipal,
        task_id: str,
    ) -> EdgeExecutionResult:
        organization_id = self._organization_id()
        task = self._execution.get_task(task_id)
        self._authorize(
            EdgeAction.TASK_EXECUTE,
            principal,
            organization_id=organization_id,
            profile_id=task.plan.profile_id,
            task=task,
            dry_run=self._execution.dry_run,
            target_id=task.task_id,
        )
        try:
            result = self._execution.execute_task(task_id)
        except Exception as exc:
            self._record_failure(
                principal,
                EdgeAction.TASK_EXECUTE,
                exc,
                target_id=task.task_id,
                plan_digest=task.plan.digest(),
                dry_run=self._execution.dry_run,
            )
            raise
        self._record(
            principal,
            EdgeAction.TASK_EXECUTE,
            EdgeAuditOutcome.SUCCEEDED,
            "task_simulated" if result.evidence.dry_run else "task_executed",
            target_id=result.task.task_id,
            plan_digest=result.task.plan.digest(),
            dry_run=result.evidence.dry_run,
        )
        return result

    def cancel_task(
        self,
        principal: EdgePrincipal,
        task_id: str,
    ) -> EdgeExecutionTask:
        organization_id = self._organization_id()
        task = self._execution.get_task(task_id)
        self._authorize(
            EdgeAction.TASK_CANCEL,
            principal,
            organization_id=organization_id,
            profile_id=task.plan.profile_id,
            task=task,
            target_id=task.task_id,
        )
        try:
            cancelled = self._execution.cancel_task(task_id)
        except Exception as exc:
            self._record_failure(
                principal,
                EdgeAction.TASK_CANCEL,
                exc,
                target_id=task.task_id,
            )
            raise
        self._record(
            principal,
            EdgeAction.TASK_CANCEL,
            EdgeAuditOutcome.SUCCEEDED,
            "task_cancelled",
            target_id=cancelled.task_id,
            plan_digest=cancelled.plan.digest(),
            dry_run=self._execution.dry_run,
        )
        return cancelled

    def list_audit(
        self,
        principal: EdgePrincipal,
        *,
        limit: int = 100,
    ) -> tuple[EdgeAuditEvent, ...]:
        organization_id = self._organization_id()
        self._authorize(
            EdgeAction.AUDIT_READ,
            principal,
            organization_id=organization_id,
        )
        events = self._audit.query(principal.organization_id, limit=limit)
        self._record(
            principal,
            EdgeAction.AUDIT_READ,
            EdgeAuditOutcome.SUCCEEDED,
            "audit_read",
        )
        return events

    def authorize_onboarding_action(
        self,
        principal: EdgePrincipal,
        action: EdgeAction,
        *,
        onboarding_id: str | None = None,
    ) -> None:
        """Authorize one of the orchestration-only onboarding actions."""

        if action not in {
            EdgeAction.ONBOARDING_LIST,
            EdgeAction.ONBOARDING_CANCEL,
            EdgeAction.ONBOARDING_RECONCILE,
        }:
            raise ValueError("A ação não pertence ao workflow de onboarding.")
        self._authorize(
            action,
            principal,
            organization_id=self._organization_id(),
            target_id=onboarding_id,
        )

    def record_onboarding_outcome(
        self,
        principal: EdgePrincipal,
        action: EdgeAction,
        outcome: EdgeAuditOutcome,
        reason_code: str,
        *,
        onboarding_id: str | None = None,
    ) -> None:
        """Record the result of an authorized onboarding orchestration action."""

        if action not in {
            EdgeAction.ONBOARDING_LIST,
            EdgeAction.ONBOARDING_CANCEL,
            EdgeAction.ONBOARDING_RECONCILE,
        }:
            raise ValueError("A ação não pertence ao workflow de onboarding.")
        if outcome not in {
            EdgeAuditOutcome.SUCCEEDED,
            EdgeAuditOutcome.FAILED,
        }:
            raise ValueError("O resultado final do onboarding é inválido.")
        self._record(
            principal,
            action,
            outcome,
            reason_code,
            target_id=onboarding_id,
            dry_run=self._execution.dry_run,
        )

    def discard_pending_plan(self, token: str) -> None:
        """Discard one transient plan after an orchestration rollback."""

        self._profiles.revoke_pending_configuration(token)

    def discard_authorization(self, authorization_id: str) -> None:
        """Discard one transient authorization after an orchestration rollback."""

        self._profiles.revoke_authorized_configuration(authorization_id)

    def _authorize(
        self,
        action: EdgeAction,
        principal: EdgePrincipal,
        *,
        organization_id: str,
        profile_id: str | None = None,
        plan=None,
        task=None,
        dry_run: bool = True,
        target_id: str | None = None,
    ) -> None:
        try:
            self._policy.require(
                action,
                principal,
                target_organization_id=organization_id,
                profile_id=profile_id,
                plan=plan,
                task=task,
                dry_run=dry_run,
            )
        except EdgePolicyDenied as exc:
            self._record(
                principal,
                action,
                EdgeAuditOutcome.DENIED,
                exc.reason_code,
                target_id=target_id,
                plan_digest=plan.digest() if plan is not None else None,
                dry_run=dry_run if action is EdgeAction.TASK_EXECUTE else None,
            )
            raise
        self._record(
            principal,
            action,
            EdgeAuditOutcome.AUTHORIZED,
            "policy_authorized",
            target_id=target_id,
            plan_digest=plan.digest() if plan is not None else None,
            dry_run=dry_run if action is EdgeAction.TASK_EXECUTE else None,
        )

    def _record_failure(
        self,
        principal: EdgePrincipal,
        action: EdgeAction,
        error: Exception,
        *,
        target_id: str | None = None,
        plan_digest: str | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self._record(
            principal,
            action,
            EdgeAuditOutcome.FAILED,
            _safe_failure_code(error),
            target_id=target_id,
            plan_digest=plan_digest,
            dry_run=dry_run,
        )

    def _record(
        self,
        principal: EdgePrincipal,
        action: EdgeAction,
        outcome: EdgeAuditOutcome,
        reason_code: str,
        *,
        target_id: str | None = None,
        plan_digest: str | None = None,
        dry_run: bool | None = None,
    ) -> None:
        self._audit.record(
            build_edge_audit_event(
                principal,
                device_id=self._agent.state.identity.device_id,
                action=action,
                outcome=outcome,
                reason_code=reason_code,
                occurred_at=self._now(),
                target_id=target_id,
                plan_digest=plan_digest,
                dry_run=dry_run,
                organization_id=self._organization_id(),
            )
        )

    def _organization_id(self) -> str:
        enrollment = self._agent.state.enrollment
        if enrollment is None:
            raise PermissionError("O dispositivo ainda não está cadastrado.")
        if self._agent.state.paused:
            raise PermissionError("O Atlas Edge está pausado neste dispositivo.")
        return enrollment.organization_id

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("O relógio de governança deve possuir fuso horário.")
        return value.astimezone(timezone.utc)


def _safe_failure_code(error: Exception) -> str:
    if isinstance(error, PermissionError):
        return "permission_denied"
    if isinstance(error, ValueError):
        return "validation_failed"
    if isinstance(error, RuntimeError):
        return "operation_failed"
    return "internal_error"
