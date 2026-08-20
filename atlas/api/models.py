"""Contratos públicos dos endpoints de observabilidade."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic import field_validator


class ApiModel(BaseModel):
    """Configuração comum para respostas imutáveis da API."""

    model_config = ConfigDict(frozen=True)


class HealthResponse(ApiModel):
    """Confirma que o processo HTTP está respondendo."""

    status: Literal["ok"] = "ok"
    service: str = "atlas-api"
    timestamp: datetime


class VersionResponse(ApiModel):
    """Identifica as versões do produto e do contrato HTTP."""

    name: str
    version: str
    api_version: str


class ResourceUsage(ApiModel):
    """Uso instantâneo e não sensível dos recursos da máquina."""

    cpu_percent: float = Field(ge=0.0, le=100.0)
    memory_percent: float = Field(ge=0.0, le=100.0)


class CapabilityStatus(ApiModel):
    """Recursos disponíveis na instalação atual do Atlas."""

    workflow: bool = True
    scheduler: bool = True
    memory: bool = True
    voice: bool
    microphone: bool
    wake_word: bool
    specialized_agents: tuple[str, ...]


class StatusResponse(ApiModel):
    """Visão operacional leve do serviço local."""

    status: Literal["ready"] = "ready"
    name: str
    version: str
    api_version: str
    mode: Literal["local"] = "local"
    local_only: bool = True
    authentication_required: bool = True
    uptime_seconds: float = Field(ge=0.0)
    resources: ResourceUsage
    capabilities: CapabilityStatus


class PrincipalResponse(ApiModel):
    """Identidade autenticada sem qualquer material secreto."""

    principal_id: str
    role: str
    scopes: tuple[str, ...]


class CommandRequest(ApiModel):
    """Comando de linguagem natural enviado ao núcleo."""

    command: str = Field(min_length=1, max_length=4000)

    @field_validator("command")
    @classmethod
    def normalize_command(cls, value: str) -> str:
        command = value.strip()

        if not command:
            raise ValueError("O comando não pode estar vazio.")

        return command


class CommandResponse(ApiModel):
    """Resultado estruturado de uma execução autenticada."""

    request_id: str
    message: str
    source: str
    success: bool
    action_count: int = Field(ge=0)
    cancelled: bool
    should_close: bool
    duration_ms: float = Field(ge=0.0)


class WorkflowCancellationRequest(ApiModel):
    """Motivo opcional para uma solicitação de cancelamento."""

    reason: str = Field(
        default="Cancelado pela API.",
        min_length=1,
        max_length=500,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        reason = value.strip()

        if not reason:
            raise ValueError("O motivo não pode estar vazio.")

        return reason


class WorkflowStatusResponse(ApiModel):
    """Estado, progresso e resultado de uma execução submetida à API."""

    workflow_id: str
    status: Literal["running", "completed", "failed", "cancelled"]
    requested_by: str | None
    created_at: datetime
    started_at: datetime
    finished_at: datetime | None
    duration_ms: float = Field(ge=0.0)
    progress: float = Field(ge=0.0, le=1.0)
    completed_steps: int = Field(ge=0)
    total_steps: int = Field(ge=0)
    current_step: str | None
    message: str | None
    source: str | None
    success: bool | None
    cancelled: bool
    cancellation_requested: bool
    cancellation_reason: str | None
    cancellation_requested_by: str | None


class AuditEventResponse(ApiModel):
    """Evento sanitizado da trilha persistente da API."""

    event_id: str
    event_type: str
    occurred_at: datetime
    principal_id: str | None
    workflow_id: str | None
    outcome: Literal[
        "accepted",
        "succeeded",
        "rejected",
        "failed",
        "timed_out",
        "cancel_requested",
        "cancelled",
    ]
    status_code: int = Field(ge=100, le=599)
    duration_ms: float | None = Field(default=None, ge=0.0)
    details: dict[str, JsonValue]


class AuditEventsResponse(ApiModel):
    """Página limitada de eventos, ordenada do mais recente ao mais antigo."""

    items: tuple[AuditEventResponse, ...]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)


class OperationalSessionResponse(ApiModel):
    """Resumo seguro de uma sessão operacional persistida."""

    session_id: str
    user_id: str
    title: str
    status: Literal["active", "paused", "completed", "failed", "cancelled"]
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    current: bool


class OperationalSessionsResponse(ApiModel):
    """Lista limitada de sessões pertencentes ao usuário local."""

    items: tuple[OperationalSessionResponse, ...]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)


class OperationalEventResponse(ApiModel):
    """Evento estruturado da linha do tempo de uma sessão."""

    event_id: str
    session_id: str
    sequence: int = Field(ge=1)
    event_type: str
    occurred_at: datetime
    message: str
    workflow_id: str | None
    action_type: str | None
    details: dict[str, JsonValue]


class OperationalTimelineResponse(ApiModel):
    """Página cronológica de eventos operacionais persistidos."""

    session_id: str
    items: tuple[OperationalEventResponse, ...]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    latest_sequence: int | None = Field(default=None, ge=1)


class ResumableStepResponse(ApiModel):
    """Etapa ainda pendente em um plano de retomada."""

    step_index: int = Field(ge=0)
    step_number: int = Field(ge=1)
    action_type: str
    parameters: dict[str, JsonValue]
    risk: Literal["safe", "confirmation_required", "blocked"]
    reason: str


class ResumptionPlanResponse(ApiModel):
    """Decisão auditável sobre o último workflow interrompido."""

    session_id: str
    status: Literal[
        "not_available",
        "ready",
        "confirmation_required",
        "blocked",
    ]
    reason: str
    source_workflow_id: str | None
    source_sequence: int | None = Field(default=None, ge=1)
    total_steps: int = Field(ge=0)
    completed_step_indexes: tuple[int, ...]
    remaining_steps: tuple[ResumableStepResponse, ...]
    confirmation_token: str | None
    requires_confirmation: bool
    can_resume: bool


class WorkflowResumptionRequest(ApiModel):
    """Confirmação opcional para executar uma retomada pendente."""

    confirmation_token: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )

    @field_validator("confirmation_token")
    @classmethod
    def normalize_confirmation_token(cls, value: str | None) -> str | None:
        if value is None:
            return None

        token = value.strip()

        if not token:
            raise ValueError("O token de confirmação não pode estar vazio.")

        return token


class WorkflowResumptionResponse(ApiModel):
    """Resultado de uma solicitação explícita de retomada."""

    request_id: str
    message: str
    success: bool
    action_count: int = Field(ge=0)
    reason_code: str | None
    duration_ms: float = Field(ge=0.0)
