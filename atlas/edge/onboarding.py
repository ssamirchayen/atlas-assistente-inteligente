"""Persistent, privacy-safe employee onboarding contracts for Atlas Edge."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping
import re
from uuid import uuid4

from atlas.edge.models import normalize_organization_id


_ONBOARDING_ID = re.compile(r"^edgeonb_[a-f0-9]{32}$")
_DEVICE_ID = re.compile(r"^edge_[a-f0-9]{32}$")
_REQUEST_ID = re.compile(r"^edgeplan_[a-f0-9]{32}$")
_TASK_ID = re.compile(r"^edgetask_[a-f0-9]{32}$")
_PROFILE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_EVIDENCE_ID = re.compile(r"^[a-f0-9]{32}$")
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SAFE_RESULT = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class EmployeeOnboardingStatus(StrEnum):
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    AUTHORIZED = "authorized"
    QUEUED = "queued"
    RUNNING = "running"
    ACTION_REQUIRED = "action_required"
    SIMULATED = "simulated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATUSES = {
    EmployeeOnboardingStatus.SIMULATED,
    EmployeeOnboardingStatus.SUCCEEDED,
    EmployeeOnboardingStatus.FAILED,
    EmployeeOnboardingStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class EmployeeOnboarding:
    """Restart-safe workflow state containing hashes and safe IDs only."""

    organization_id: str
    device_id: str
    employee_reference_hash: str
    requester_hash: str
    profile_id: str
    status: EmployeeOnboardingStatus
    created_at: datetime
    updated_at: datetime
    onboarding_id: str = field(default_factory=lambda: f"edgeonb_{uuid4().hex}")
    plan_request_id: str | None = None
    plan_digest: str | None = None
    task_id: str | None = None
    evidence_id: str | None = None
    result_status: str | None = None
    error_code: str | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        if not _ONBOARDING_ID.fullmatch(self.onboarding_id):
            raise ValueError("O identificador do onboarding é inválido.")
        if not _DEVICE_ID.fullmatch(self.device_id):
            raise ValueError("O dispositivo do onboarding é inválido.")
        if not _PROFILE_ID.fullmatch(self.profile_id):
            raise ValueError("O perfil do onboarding é inválido.")
        for field_name, value in (
            ("employee_reference_hash", self.employee_reference_hash),
            ("requester_hash", self.requester_hash),
        ):
            if not _DIGEST.fullmatch(value):
                raise ValueError(f"{field_name} deve ser um SHA-256.")
        if not isinstance(self.status, EmployeeOnboardingStatus):
            raise TypeError("status deve ser EmployeeOnboardingStatus.")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("A atualização não pode preceder a criação.")
        if self.plan_request_id is not None and not _REQUEST_ID.fullmatch(
            self.plan_request_id
        ):
            raise ValueError("A solicitação de plano do onboarding é inválida.")
        if self.plan_digest is not None and not _DIGEST.fullmatch(
            self.plan_digest
        ):
            raise ValueError("O digest do plano do onboarding é inválido.")
        if self.task_id is not None and not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("A tarefa do onboarding é inválida.")
        if self.evidence_id is not None and not _EVIDENCE_ID.fullmatch(
            self.evidence_id
        ):
            raise ValueError("A evidência do onboarding é inválida.")
        if self.result_status is not None and not _SAFE_RESULT.fullmatch(
            self.result_status
        ):
            raise ValueError("O resultado do onboarding é inválido.")
        if self.error_code is not None and not _SAFE_CODE.fullmatch(
            self.error_code
        ):
            raise ValueError("O código de erro do onboarding é inválido.")
        if self.revision <= 0:
            raise ValueError("A revisão do onboarding deve ser positiva.")
        object.__setattr__(
            self,
            "organization_id",
            normalize_organization_id(self.organization_id),
        )
        object.__setattr__(
            self,
            "created_at",
            self.created_at.astimezone(timezone.utc),
        )
        object.__setattr__(
            self,
            "updated_at",
            self.updated_at.astimezone(timezone.utc),
        )

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def as_dict(self) -> dict[str, object]:
        return {
            "onboarding_id": self.onboarding_id,
            "organization_id": self.organization_id,
            "device_id": self.device_id,
            "employee_reference_hash": self.employee_reference_hash,
            "requester_hash": self.requester_hash,
            "profile_id": self.profile_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "plan_request_id": self.plan_request_id,
            "plan_digest": self.plan_digest,
            "task_id": self.task_id,
            "evidence_id": self.evidence_id,
            "result_status": self.result_status,
            "error_code": self.error_code,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EmployeeOnboarding":
        try:
            status = EmployeeOnboardingStatus(str(payload.get("status", "")))
        except ValueError as exc:
            raise ValueError("O status persistido do onboarding é inválido.") from exc
        return cls(
            onboarding_id=str(payload.get("onboarding_id", "")),
            organization_id=str(payload.get("organization_id", "")),
            device_id=str(payload.get("device_id", "")),
            employee_reference_hash=str(
                payload.get("employee_reference_hash", "")
            ),
            requester_hash=str(payload.get("requester_hash", "")),
            profile_id=str(payload.get("profile_id", "")),
            status=status,
            created_at=_datetime(payload.get("created_at"), "created_at"),
            updated_at=_datetime(payload.get("updated_at"), "updated_at"),
            plan_request_id=_optional(payload.get("plan_request_id")),
            plan_digest=_optional(payload.get("plan_digest")),
            task_id=_optional(payload.get("task_id")),
            evidence_id=_optional(payload.get("evidence_id")),
            result_status=_optional(payload.get("result_status")),
            error_code=_optional(payload.get("error_code")),
            revision=_integer(payload.get("revision", 1), "revision"),
        )


@dataclass(frozen=True, slots=True)
class EmployeeOnboardingReport:
    organization_id: str
    total: int
    active: int
    action_required: int
    simulated: int
    succeeded: int
    failed: int
    cancelled: int
    generated_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "organization_id",
            normalize_organization_id(self.organization_id),
        )
        values = (
            self.total,
            self.active,
            self.action_required,
            self.simulated,
            self.succeeded,
            self.failed,
            self.cancelled,
        )
        if any(value < 0 for value in values):
            raise ValueError("Os contadores do relatório não podem ser negativos.")
        if self.total != sum(values[1:]):
            raise ValueError("Os contadores do relatório não fecham o total.")
        _aware(self.generated_at, "generated_at")


def _datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} é inválido.") from exc
    _aware(parsed, field_name)
    return parsed.astimezone(timezone.utc)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} deve possuir fuso horário.")


def _optional(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} deve ser inteiro.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} deve ser inteiro.") from exc
