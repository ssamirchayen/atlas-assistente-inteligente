"""Aplicação FastAPI do Atlas."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware

from atlas.api.audit import (
    AuditEvent,
    AuditOutcome,
    AuditStorageError,
    AuditTrail,
    NullAuditTrail,
    SqliteAuditTrail,
    sensitive_fingerprint,
)

from atlas.api.auth import (
    AUDIT_READ,
    COMMANDS_EXECUTE,
    SESSIONS_READ,
    STATUS_READ,
    WORKFLOWS_CANCEL,
    WORKFLOWS_READ,
    WORKFLOWS_RESUME,
    ApiKeyAuthenticator,
    ApiPrincipal,
    create_authentication_dependency,
    create_scope_dependency,
)
from atlas.api.models import (
    AuditEventResponse,
    AuditEventsResponse,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    OperationalEventResponse,
    OperationalSessionResponse,
    OperationalSessionsResponse,
    OperationalTimelineResponse,
    PrincipalResponse,
    ResumableStepResponse,
    ResumptionPlanResponse,
    StatusResponse,
    VersionResponse,
    WorkflowCancellationRequest,
    WorkflowResumptionRequest,
    WorkflowResumptionResponse,
    WorkflowStatusResponse,
)
from atlas.api.runtime import (
    AtlasApiRuntime,
    CommandRuntime,
    RuntimeBusyError,
    RuntimeClosedError,
    RuntimeTimeoutError,
    RuntimeWorkflowNotCancellableError,
    RuntimeWorkflowNotFoundError,
    WorkflowRuntimeSnapshot,
)
from atlas.api.status import AtlasStatusService
from atlas.session.models import (
    OperationalEvent,
    OperationalSession,
    SessionStatus,
)
from atlas.session.resumption import ResumptionPlan
from atlas.session.storage import SessionStorageError
from atlas.version import API_VERSION, ATLAS_VERSION

_LOGGER = logging.getLogger(__name__)
_TRUSTED_HOSTS = ["127.0.0.1", "localhost", "testserver"]


def _workflow_response(
    snapshot: WorkflowRuntimeSnapshot,
) -> WorkflowStatusResponse:
    return WorkflowStatusResponse(
        workflow_id=snapshot.workflow_id,
        status=snapshot.status,
        requested_by=snapshot.requested_by,
        created_at=snapshot.created_at,
        started_at=snapshot.started_at,
        finished_at=snapshot.finished_at,
        duration_ms=snapshot.duration_ms,
        progress=snapshot.progress,
        completed_steps=snapshot.completed_steps,
        total_steps=snapshot.total_steps,
        current_step=snapshot.current_step,
        message=snapshot.message,
        source=snapshot.source,
        success=snapshot.success,
        cancelled=snapshot.cancelled,
        cancellation_requested=snapshot.cancellation_requested,
        cancellation_reason=snapshot.cancellation_reason,
        cancellation_requested_by=snapshot.cancellation_requested_by,
    )


def _audit_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        principal_id=event.principal_id,
        workflow_id=event.workflow_id,
        outcome=event.outcome,
        status_code=event.status_code,
        duration_ms=event.duration_ms,
        details=event.details,
    )


def _session_response(
    session: OperationalSession,
    *,
    current_session_id: str | None,
) -> OperationalSessionResponse:
    return OperationalSessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        title=session.title,
        status=session.status.value,
        created_at=session.created_at,
        updated_at=session.updated_at,
        ended_at=session.ended_at,
        current=session.session_id == current_session_id,
    )


def _operational_event_response(
    event: OperationalEvent,
) -> OperationalEventResponse:
    return OperationalEventResponse(
        event_id=event.event_id,
        session_id=event.session_id,
        sequence=event.sequence,
        event_type=event.event_type.value,
        occurred_at=event.occurred_at,
        message=event.message,
        workflow_id=event.workflow_id,
        action_type=event.action_type,
        details=dict(event.details),
    )


def _resumption_plan_response(
    plan: ResumptionPlan,
) -> ResumptionPlanResponse:
    return ResumptionPlanResponse(
        session_id=plan.session_id,
        status=plan.status.value,
        reason=plan.reason,
        source_workflow_id=plan.source_workflow_id,
        source_sequence=plan.source_sequence,
        total_steps=plan.total_steps,
        completed_step_indexes=plan.completed_step_indexes,
        remaining_steps=tuple(
            ResumableStepResponse(
                step_index=step.step_index,
                step_number=step.step_number,
                action_type=step.action_type,
                parameters=dict(step.parameters),
                risk=step.risk.value,
                reason=step.reason,
            )
            for step in plan.remaining_steps
        ),
        confirmation_token=plan.confirmation_token,
        requires_confirmation=plan.requires_confirmation,
        can_resume=plan.can_resume,
    )


def create_app(
    status_service: AtlasStatusService | None = None,
    authenticator: ApiKeyAuthenticator | None = None,
    command_runtime: CommandRuntime | None = None,
    audit_trail: AuditTrail | None = None,
) -> FastAPI:
    """Cria a aplicação sem inicializar GUI, voz ou automação."""

    service = status_service or AtlasStatusService()
    api_authenticator = authenticator or ApiKeyAuthenticator.from_environment()
    runtime = command_runtime or AtlasApiRuntime()
    audit = audit_trail or NullAuditTrail()

    def record_audit(
        event_type: str,
        *,
        outcome: AuditOutcome,
        status_code: int,
        principal_id: str | None = None,
        workflow_id: str | None = None,
        duration_ms: float | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        try:
            audit.record(
                event_type,
                outcome=outcome,
                status_code=status_code,
                principal_id=principal_id,
                workflow_id=workflow_id,
                duration_ms=duration_ms,
                details=details,
            )
        except AuditStorageError:
            _LOGGER.exception(
                "Falha ao persistir evento de auditoria tipo=%s",
                event_type,
            )

    def observe_authentication(
        event_type: str,
        path: str,
        principal: ApiPrincipal | None,
        credential_present: bool,
        status_code: int,
    ) -> None:
        outcome: AuditOutcome

        if status_code == 200:
            outcome = "succeeded"
        elif status_code == 401:
            outcome = "rejected"
        else:
            outcome = "failed"

        details: dict[str, object] = {
            "path": path,
            "credential_present": credential_present,
        }

        if principal is not None:
            details["role"] = principal.role

        record_audit(
            event_type,
            outcome=outcome,
            status_code=status_code,
            principal_id=(
                principal.principal_id if principal is not None else None
            ),
            details=details,
        )

    authenticate = create_authentication_dependency(
        api_authenticator,
        observer=observe_authentication,
    )
    require_status_read = create_scope_dependency(authenticate, STATUS_READ)
    require_command_execute = create_scope_dependency(
        authenticate,
        COMMANDS_EXECUTE,
    )
    require_workflow_read = create_scope_dependency(
        authenticate,
        WORKFLOWS_READ,
    )
    require_workflow_cancel = create_scope_dependency(
        authenticate,
        WORKFLOWS_CANCEL,
    )
    require_audit_read = create_scope_dependency(authenticate, AUDIT_READ)
    require_sessions_read = create_scope_dependency(
        authenticate,
        SESSIONS_READ,
    )
    require_workflow_resume = create_scope_dependency(
        authenticate,
        WORKFLOWS_RESUME,
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        try:
            yield
        finally:
            runtime.close()
            audit.close()

    application = FastAPI(
        title="Atlas Local API",
        summary="API local do assistente inteligente Atlas.",
        version=ATLAS_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": False},
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_TRUSTED_HOSTS,
    )

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"

        if request.url.path.startswith(f"/api/{API_VERSION}"):
            response.headers["Cache-Control"] = "no-store"

        return response

    router = APIRouter(prefix=f"/api/{API_VERSION}")

    @router.get(
        "/health",
        response_model=HealthResponse,
        tags=["Observabilidade"],
        summary="Verifica se a API está respondendo",
    )
    def health() -> HealthResponse:
        return service.health()

    @router.get(
        "/version",
        response_model=VersionResponse,
        tags=["Observabilidade"],
        summary="Retorna as versões do Atlas e da API",
    )
    def version() -> VersionResponse:
        return service.version()

    @router.get(
        "/status",
        response_model=StatusResponse,
        tags=["Observabilidade"],
        summary="Retorna o estado operacional local",
        responses={401: {}, 403: {}, 503: {}},
    )
    def status(
        _principal: ApiPrincipal = Depends(require_status_read),
    ) -> StatusResponse:
        return service.status()

    @router.get(
        "/auth/me",
        response_model=PrincipalResponse,
        tags=["Autenticação"],
        summary="Retorna a identidade e as permissões da chave",
        responses={401: {}, 503: {}},
    )
    def authenticated_principal(
        principal: ApiPrincipal = Depends(authenticate),
    ) -> PrincipalResponse:
        return PrincipalResponse(
            principal_id=principal.principal_id,
            role=principal.role,
            scopes=tuple(sorted(principal.scopes)),
        )

    @router.get(
        "/sessions",
        response_model=OperationalSessionsResponse,
        tags=["Sessões"],
        summary="Lista sessões operacionais persistidas",
        responses={401: {}, 403: {}, 503: {}, 504: {}},
    )
    def operational_sessions(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        session_status: SessionStatus | None = None,
        _principal: ApiPrincipal = Depends(require_sessions_read),
    ) -> OperationalSessionsResponse:
        try:
            sessions = runtime.list_operational_sessions(
                status=session_status,
                limit=limit,
            )
            current_session_id = next(
                (
                    session.session_id
                    for session in sessions
                    if session.status is SessionStatus.ACTIVE
                ),
                None,
            )
        except RuntimeTimeoutError as error:
            raise HTTPException(
                status_code=504,
                detail="A consulta de sessões excedeu o tempo limite.",
            ) from error
        except (RuntimeClosedError, SessionStorageError) as error:
            raise HTTPException(
                status_code=503,
                detail="As sessões operacionais estão indisponíveis.",
            ) from error

        return OperationalSessionsResponse(
            items=tuple(
                _session_response(
                    session,
                    current_session_id=current_session_id,
                )
                for session in sessions
            ),
            count=len(sessions),
            limit=limit,
        )

    @router.get(
        "/sessions/{session_id}/timeline",
        response_model=OperationalTimelineResponse,
        tags=["Sessões"],
        summary="Consulta a linha do tempo operacional de uma sessão",
        responses={401: {}, 403: {}, 404: {}, 503: {}, 504: {}},
    )
    def operational_timeline(
        session_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        after_sequence: Annotated[int | None, Query(ge=0)] = None,
        _principal: ApiPrincipal = Depends(require_sessions_read),
    ) -> OperationalTimelineResponse:
        try:
            events = runtime.get_operational_timeline(
                session_id=session_id,
                limit=limit,
                after_sequence=after_sequence,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail="Sessão operacional não encontrada.",
            ) from error
        except RuntimeTimeoutError as error:
            raise HTTPException(
                status_code=504,
                detail="A consulta da linha do tempo excedeu o limite.",
            ) from error
        except (RuntimeClosedError, SessionStorageError) as error:
            raise HTTPException(
                status_code=503,
                detail="A linha do tempo está indisponível.",
            ) from error

        return OperationalTimelineResponse(
            session_id=session_id,
            items=tuple(
                _operational_event_response(event) for event in events
            ),
            count=len(events),
            limit=limit,
            latest_sequence=events[-1].sequence if events else None,
        )

    @router.get(
        "/resumption",
        response_model=ResumptionPlanResponse,
        tags=["Retomada"],
        summary="Consulta o plano seguro do workflow interrompido",
        responses={401: {}, 403: {}, 503: {}, 504: {}},
    )
    def resumption_plan(
        _principal: ApiPrincipal = Depends(require_sessions_read),
    ) -> ResumptionPlanResponse:
        try:
            plan = runtime.get_resumption_plan()
        except RuntimeTimeoutError as error:
            raise HTTPException(
                status_code=504,
                detail="A consulta de retomada excedeu o tempo limite.",
            ) from error
        except (RuntimeClosedError, SessionStorageError) as error:
            raise HTTPException(
                status_code=503,
                detail="O plano de retomada está indisponível.",
            ) from error

        return _resumption_plan_response(plan)

    @router.post(
        "/resumption",
        response_model=WorkflowResumptionResponse,
        tags=["Retomada"],
        summary="Executa explicitamente uma retomada segura",
        responses={401: {}, 403: {}, 409: {}, 503: {}, 504: {}},
    )
    def resume_interrupted_workflow(
        payload: WorkflowResumptionRequest | None = None,
        principal: ApiPrincipal = Depends(require_workflow_resume),
    ) -> WorkflowResumptionResponse:
        request_id = str(uuid4())
        started_at = perf_counter()
        record_audit(
            "workflow.resume_requested",
            outcome="accepted",
            status_code=202,
            principal_id=principal.principal_id,
            workflow_id=request_id,
            details={
                "confirmation_present": bool(
                    payload and payload.confirmation_token
                )
            },
        )

        try:
            result = runtime.resume_interrupted_workflow(
                confirmation_token=(
                    payload.confirmation_token if payload is not None else None
                ),
                workflow_id=request_id,
                requested_by=principal.principal_id,
            )
        except RuntimeBusyError as error:
            raise HTTPException(
                status_code=409,
                detail="O Atlas já está executando outro workflow.",
            ) from error
        except RuntimeTimeoutError as error:
            raise HTTPException(
                status_code=504,
                detail=(
                    "A espera da API terminou. Consulte o workflow pelo "
                    "identificador retornado."
                ),
                headers={"X-Workflow-ID": request_id},
            ) from error
        except RuntimeClosedError as error:
            raise HTTPException(
                status_code=503,
                detail="O runtime de comandos está encerrado.",
            ) from error

        duration_ms = round((perf_counter() - started_at) * 1000, 3)
        record_audit(
            "workflow.resume_completed",
            outcome="succeeded" if result.success else "rejected",
            status_code=200,
            principal_id=principal.principal_id,
            workflow_id=request_id,
            duration_ms=duration_ms,
            details={
                "action_count": result.action_count,
                "reason_code": result.reason_code,
            },
        )
        return WorkflowResumptionResponse(
            request_id=request_id,
            message=result.message,
            success=result.success,
            action_count=result.action_count,
            reason_code=result.reason_code,
            duration_ms=duration_ms,
        )

    @router.post(
        "/commands",
        response_model=CommandResponse,
        tags=["Comandos"],
        summary="Executa um comando no núcleo do Atlas",
        responses={401: {}, 403: {}, 409: {}, 503: {}, 504: {}},
    )
    def execute_command(
        payload: CommandRequest,
        principal: ApiPrincipal = Depends(require_command_execute),
    ) -> CommandResponse:
        request_id = str(uuid4())
        started_at = perf_counter()
        command_details = sensitive_fingerprint(
            "command",
            payload.command,
        )
        record_audit(
            "command.received",
            outcome="accepted",
            status_code=202,
            principal_id=principal.principal_id,
            workflow_id=request_id,
            details=command_details,
        )

        try:
            result = runtime.execute(
                payload.command,
                workflow_id=request_id,
                requested_by=principal.principal_id,
            )
        except RuntimeBusyError as error:
            record_audit(
                "command.rejected",
                outcome="rejected",
                status_code=409,
                principal_id=principal.principal_id,
                workflow_id=request_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                details={
                    **command_details,
                    "reason_code": "runtime_busy",
                },
            )
            raise HTTPException(
                status_code=409,
                detail="O Atlas já está executando outro comando.",
            ) from error
        except RuntimeTimeoutError as error:
            record_audit(
                "command.timed_out",
                outcome="timed_out",
                status_code=504,
                principal_id=principal.principal_id,
                workflow_id=request_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                details=command_details,
            )
            raise HTTPException(
                status_code=504,
                detail=(
                    "O tempo de espera da API terminou. A execução continua "
                    "no núcleo até concluir ou ser cancelada."
                ),
                headers={"X-Workflow-ID": request_id},
            ) from error
        except RuntimeClosedError as error:
            record_audit(
                "command.rejected",
                outcome="rejected",
                status_code=503,
                principal_id=principal.principal_id,
                workflow_id=request_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                details={
                    **command_details,
                    "reason_code": "runtime_closed",
                },
            )
            raise HTTPException(
                status_code=503,
                detail="O runtime de comandos está encerrado.",
            ) from error
        except Exception as error:
            _LOGGER.exception(
                "Falha na execução da API request_id=%s principal=%s",
                request_id,
                principal.principal_id,
            )
            record_audit(
                "command.failed",
                outcome="failed",
                status_code=500,
                principal_id=principal.principal_id,
                workflow_id=request_id,
                duration_ms=(perf_counter() - started_at) * 1000,
                details=command_details,
            )
            raise HTTPException(
                status_code=500,
                detail="Falha interna ao executar o comando.",
            ) from error

        duration_ms = round((perf_counter() - started_at) * 1000, 3)
        outcome: AuditOutcome

        if result.cancelled:
            outcome = "cancelled"
        elif result.success:
            outcome = "succeeded"
        else:
            outcome = "failed"

        record_audit(
            "command.completed",
            outcome=outcome,
            status_code=200,
            principal_id=principal.principal_id,
            workflow_id=request_id,
            duration_ms=duration_ms,
            details={
                **command_details,
                "source": result.source,
                "action_count": result.action_count,
                "should_close": result.should_close,
            },
        )

        return CommandResponse(
            request_id=request_id,
            message=result.message,
            source=result.source,
            success=result.success,
            action_count=result.action_count,
            cancelled=result.cancelled,
            should_close=result.should_close,
            duration_ms=duration_ms,
        )

    @router.get(
        "/workflows/{workflow_id}",
        response_model=WorkflowStatusResponse,
        tags=["Workflows"],
        summary="Consulta o estado e o resultado de um workflow",
        responses={401: {}, 403: {}, 404: {}, 503: {}},
    )
    def workflow_status(
        workflow_id: str,
        principal: ApiPrincipal = Depends(require_workflow_read),
    ) -> WorkflowStatusResponse:
        try:
            snapshot = runtime.get_workflow(workflow_id)
        except RuntimeWorkflowNotFoundError as error:
            record_audit(
                "workflow.lookup_rejected",
                outcome="rejected",
                status_code=404,
                principal_id=principal.principal_id,
                workflow_id=workflow_id,
                details={"reason_code": "workflow_not_found"},
            )
            raise HTTPException(
                status_code=404,
                detail="Workflow não encontrado.",
            ) from error

        return _workflow_response(snapshot)

    @router.post(
        "/workflows/{workflow_id}/cancel",
        response_model=WorkflowStatusResponse,
        status_code=202,
        tags=["Workflows"],
        summary="Solicita o cancelamento cooperativo de um workflow",
        responses={401: {}, 403: {}, 404: {}, 409: {}, 503: {}},
    )
    def cancel_workflow(
        workflow_id: str,
        payload: WorkflowCancellationRequest | None = None,
        principal: ApiPrincipal = Depends(require_workflow_cancel),
    ) -> WorkflowStatusResponse:
        reason = (
            payload.reason
            if payload is not None
            else "Cancelado pela API."
        )

        try:
            snapshot = runtime.cancel_workflow(
                workflow_id,
                reason=reason,
                requested_by=principal.principal_id,
            )
        except RuntimeWorkflowNotFoundError as error:
            record_audit(
                "workflow.cancel_rejected",
                outcome="rejected",
                status_code=404,
                principal_id=principal.principal_id,
                workflow_id=workflow_id,
                details={"reason_code": "workflow_not_found"},
            )
            raise HTTPException(
                status_code=404,
                detail="Workflow não encontrado.",
            ) from error
        except RuntimeWorkflowNotCancellableError as error:
            record_audit(
                "workflow.cancel_rejected",
                outcome="rejected",
                status_code=409,
                principal_id=principal.principal_id,
                workflow_id=workflow_id,
                details={"reason_code": "workflow_not_cancellable"},
            )
            raise HTTPException(
                status_code=409,
                detail="O workflow não está ativo ou não pode ser cancelado.",
            ) from error

        record_audit(
            "workflow.cancel_requested",
            outcome="cancel_requested",
            status_code=202,
            principal_id=principal.principal_id,
            workflow_id=workflow_id,
            details=sensitive_fingerprint("reason", reason),
        )

        return _workflow_response(snapshot)

    @router.get(
        "/audit/events",
        response_model=AuditEventsResponse,
        tags=["Auditoria"],
        summary="Consulta eventos sanitizados da auditoria local",
        responses={401: {}, 403: {}, 503: {}},
    )
    def audit_events(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        event_type: Annotated[
            str | None,
            Query(
                min_length=1,
                max_length=80,
                pattern=r"^[a-z][a-z0-9_.-]*$",
            ),
        ] = None,
        workflow_id: Annotated[
            str | None,
            Query(min_length=1, max_length=128),
        ] = None,
        _principal: ApiPrincipal = Depends(require_audit_read),
    ) -> AuditEventsResponse:
        try:
            events = audit.list_events(
                limit=limit,
                event_type=event_type,
                workflow_id=workflow_id,
            )
        except AuditStorageError as error:
            raise HTTPException(
                status_code=503,
                detail="A auditoria local está temporariamente indisponível.",
            ) from error

        items = tuple(_audit_response(event) for event in events)
        return AuditEventsResponse(
            items=items,
            count=len(items),
            limit=limit,
        )

    application.include_router(router)
    return application


app = create_app(audit_trail=SqliteAuditTrail())
