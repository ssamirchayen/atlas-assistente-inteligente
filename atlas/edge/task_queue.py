"""Restart-safe local queue for supervised Atlas Edge execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Callable, Mapping
from uuid import uuid4

from atlas.edge.models import normalize_organization_id
from atlas.edge.profiles import AuthorizedEdgePlan
from atlas.provisioning.models import ProvisioningEvidence, ProvisioningPlan


_TASK_ID = re.compile(r"^edgetask_[a-f0-9]{32}$")
_AUTHORIZATION_ID = re.compile(r"^edgeauth_[a-f0-9]{32}$")
_DEVICE_ID = re.compile(r"^edge_[a-f0-9]{32}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class EdgeTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SIMULATED = "simulated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


_TERMINAL_STATUSES = {
    EdgeTaskStatus.SIMULATED,
    EdgeTaskStatus.SUCCEEDED,
    EdgeTaskStatus.FAILED,
    EdgeTaskStatus.CANCELLED,
    EdgeTaskStatus.EXPIRED,
}


@dataclass(frozen=True, slots=True)
class EdgeExecutionTask:
    authorization_id: str
    device_id: str
    organization_id: str
    profile_digest: str
    employee_reference_hash: str
    approver_hash: str
    plan: ProvisioningPlan
    created_at: datetime
    expires_at: datetime
    updated_at: datetime
    task_id: str = ""
    status: EdgeTaskStatus = EdgeTaskStatus.QUEUED
    attempts: int = 0
    recovery_count: int = 0
    evidence_id: str | None = None
    result_status: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        task_id = self.task_id or f"edgetask_{uuid4().hex}"
        if not _TASK_ID.fullmatch(task_id):
            raise ValueError("O identificador da tarefa Edge é inválido.")
        if not _AUTHORIZATION_ID.fullmatch(self.authorization_id):
            raise ValueError("A autorização da tarefa é inválida.")
        if not _DEVICE_ID.fullmatch(self.device_id):
            raise ValueError("O dispositivo da tarefa é inválido.")
        organization_id = normalize_organization_id(self.organization_id)
        for field_name, value in (
            ("profile_digest", self.profile_digest),
            ("employee_reference_hash", self.employee_reference_hash),
            ("approver_hash", self.approver_hash),
        ):
            if not _HEX_DIGEST.fullmatch(value):
                raise ValueError(f"{field_name} deve ser um SHA-256.")
        if not isinstance(self.status, EdgeTaskStatus):
            raise TypeError("status deve ser EdgeTaskStatus.")
        if self.attempts < 0 or self.recovery_count < 0:
            raise ValueError("Os contadores da tarefa não podem ser negativos.")
        for field_name, value in (
            ("created_at", self.created_at),
            ("expires_at", self.expires_at),
            ("updated_at", self.updated_at),
        ):
            _require_aware(value, field_name)
        if self.expires_at <= self.created_at:
            raise ValueError("A tarefa deve possuir validade futura.")
        if self.updated_at < self.created_at:
            raise ValueError("A atualização não pode preceder a criação.")
        if self.error_code is not None and not _SAFE_CODE.fullmatch(
            self.error_code
        ):
            raise ValueError("O código de erro da tarefa é inválido.")
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "organization_id", organization_id)

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "authorization_id": self.authorization_id,
            "device_id": self.device_id,
            "organization_id": self.organization_id,
            "profile_digest": self.profile_digest,
            "employee_reference_hash": self.employee_reference_hash,
            "approver_hash": self.approver_hash,
            "plan": self.plan.as_dict(),
            "created_at": _iso(self.created_at),
            "expires_at": _iso(self.expires_at),
            "updated_at": _iso(self.updated_at),
            "status": self.status.value,
            "attempts": self.attempts,
            "recovery_count": self.recovery_count,
            "evidence_id": self.evidence_id,
            "result_status": self.result_status,
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EdgeExecutionTask":
        raw_plan = payload.get("plan")
        if not isinstance(raw_plan, dict):
            raise ValueError("O plano persistido deve ser um objeto.")
        try:
            status = EdgeTaskStatus(str(payload.get("status", "")))
        except ValueError as exc:
            raise ValueError("O status persistido não é autorizado.") from exc
        return cls(
            task_id=str(payload.get("task_id", "")),
            authorization_id=str(payload.get("authorization_id", "")),
            device_id=str(payload.get("device_id", "")),
            organization_id=str(payload.get("organization_id", "")),
            profile_digest=str(payload.get("profile_digest", "")),
            employee_reference_hash=str(
                payload.get("employee_reference_hash", "")
            ),
            approver_hash=str(payload.get("approver_hash", "")),
            plan=ProvisioningPlan.from_dict(raw_plan),
            created_at=_datetime(payload.get("created_at"), "created_at"),
            expires_at=_datetime(payload.get("expires_at"), "expires_at"),
            updated_at=_datetime(payload.get("updated_at"), "updated_at"),
            status=status,
            attempts=_integer(payload.get("attempts", 0), "attempts"),
            recovery_count=_integer(
                payload.get("recovery_count", 0),
                "recovery_count",
            ),
            evidence_id=_optional_string(payload.get("evidence_id")),
            result_status=_optional_string(payload.get("result_status")),
            error_code=_optional_string(payload.get("error_code")),
        )


class EdgeTaskStoreError(RuntimeError):
    """Fail-closed persistence error for the local execution queue."""


class EdgeTaskStore:
    def __init__(self, path: Path, *, max_bytes: int = 512 * 1024) -> None:
        self.path = Path(path)
        if max_bytes <= 0:
            raise ValueError("O limite do arquivo da fila deve ser positivo.")
        self._max_bytes = max_bytes

    def load(self) -> tuple[EdgeExecutionTask, ...]:
        if not self.path.exists():
            return ()
        try:
            if self.path.stat().st_size > self._max_bytes:
                raise EdgeTaskStoreError("O arquivo da fila excede o limite.")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                raise EdgeTaskStoreError("O formato da fila não é suportado.")
            raw_tasks = payload.get("tasks")
            if not isinstance(raw_tasks, list):
                raise EdgeTaskStoreError("A lista de tarefas é inválida.")
            return tuple(
                EdgeExecutionTask.from_dict(_mapping(item))
                for item in raw_tasks
            )
        except EdgeTaskStoreError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise EdgeTaskStoreError("O arquivo da fila está corrompido.") from exc

    def save(self, tasks: tuple[EdgeExecutionTask, ...]) -> None:
        payload = {
            "schema_version": 1,
            "tasks": [task.as_dict() for task in tasks],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self._max_bytes:
            raise EdgeTaskStoreError("A fila excede o limite permitido.")
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        except OSError as exc:
            raise EdgeTaskStoreError("Não foi possível salvar a fila.") from exc


class EdgeTaskQueue:
    def __init__(
        self,
        store: EdgeTaskStore,
        *,
        max_tasks: int = 50,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_tasks <= 0:
            raise ValueError("O limite de tarefas deve ser positivo.")
        self._store = store
        self._max_tasks = max_tasks
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._tasks = list(store.load())
        self._recover_interrupted()

    def list(self) -> tuple[EdgeExecutionTask, ...]:
        with self._lock:
            return tuple(self._tasks)

    def get(self, task_id: str) -> EdgeExecutionTask | None:
        with self._lock:
            return next(
                (task for task in self._tasks if task.task_id == task_id),
                None,
            )

    def enqueue(self, authorization: AuthorizedEdgePlan) -> EdgeExecutionTask:
        with self._lock:
            existing = next(
                (
                    task
                    for task in self._tasks
                    if task.authorization_id == authorization.authorization_id
                ),
                None,
            )
            if existing is not None:
                return existing
            self._prune_terminal()
            if len(self._tasks) >= self._max_tasks:
                raise OverflowError("A fila local atingiu o limite de tarefas.")
            preview = authorization.preview
            task = EdgeExecutionTask(
                authorization_id=authorization.authorization_id,
                device_id=preview.device_id,
                organization_id=preview.organization_id,
                profile_digest=preview.profile_digest,
                employee_reference_hash=preview.employee_reference_hash,
                approver_hash=authorization.approver_hash,
                plan=preview.plan,
                created_at=authorization.authorized_at,
                expires_at=authorization.valid_until,
                updated_at=authorization.authorized_at,
            )
            self._tasks.append(task)
            self._save()
            return task

    def claim(self, task_id: str) -> EdgeExecutionTask:
        with self._lock:
            index, task = self._require(task_id)
            now = self._now()
            if task.status is not EdgeTaskStatus.QUEUED:
                raise ValueError("A tarefa não está disponível para execução.")
            if now >= task.expires_at:
                expired = replace(
                    task,
                    status=EdgeTaskStatus.EXPIRED,
                    updated_at=now,
                    error_code="authorization_expired",
                )
                self._tasks[index] = expired
                self._save()
                raise PermissionError("A autorização da tarefa expirou.")
            running = replace(
                task,
                status=EdgeTaskStatus.RUNNING,
                attempts=task.attempts + 1,
                updated_at=now,
                error_code=None,
            )
            self._tasks[index] = running
            self._save()
            return running

    def complete(
        self,
        task_id: str,
        evidence: ProvisioningEvidence,
    ) -> EdgeExecutionTask:
        with self._lock:
            index, task = self._require(task_id)
            if task.status is not EdgeTaskStatus.RUNNING:
                raise ValueError("A tarefa não está em execução.")
            status = (
                EdgeTaskStatus.SIMULATED
                if evidence.dry_run
                else (
                    EdgeTaskStatus.SUCCEEDED
                    if evidence.status.value == "succeeded"
                    else EdgeTaskStatus.FAILED
                )
            )
            completed = replace(
                task,
                status=status,
                updated_at=self._now(),
                evidence_id=evidence.evidence_id,
                result_status=evidence.status.value,
                error_code=(None if status is not EdgeTaskStatus.FAILED else "execution_failed"),
            )
            self._tasks[index] = completed
            self._save()
            return completed

    def fail(self, task_id: str, error_code: str) -> EdgeExecutionTask:
        if not _SAFE_CODE.fullmatch(error_code):
            raise ValueError("O código de falha não é seguro.")
        with self._lock:
            index, task = self._require(task_id)
            if task.status is not EdgeTaskStatus.RUNNING:
                raise ValueError("A tarefa não está em execução.")
            failed = replace(
                task,
                status=EdgeTaskStatus.FAILED,
                updated_at=self._now(),
                error_code=error_code,
            )
            self._tasks[index] = failed
            self._save()
            return failed

    def cancel(self, task_id: str) -> EdgeExecutionTask:
        with self._lock:
            index, task = self._require(task_id)
            if task.status is not EdgeTaskStatus.QUEUED:
                raise ValueError("Somente tarefas em espera podem ser canceladas.")
            cancelled = replace(
                task,
                status=EdgeTaskStatus.CANCELLED,
                updated_at=self._now(),
                error_code="cancelled_by_operator",
            )
            self._tasks[index] = cancelled
            self._save()
            return cancelled

    def _recover_interrupted(self) -> None:
        now = self._now()
        recovered = False
        for index, task in enumerate(self._tasks):
            if task.status is EdgeTaskStatus.RUNNING:
                self._tasks[index] = replace(
                    task,
                    status=EdgeTaskStatus.QUEUED,
                    recovery_count=task.recovery_count + 1,
                    updated_at=now,
                    error_code="interrupted_recovered",
                )
                recovered = True
        if recovered:
            self._save()

    def _prune_terminal(self) -> None:
        while len(self._tasks) >= self._max_tasks:
            index = next(
                (
                    current
                    for current, task in enumerate(self._tasks)
                    if task.terminal
                ),
                None,
            )
            if index is None:
                break
            self._tasks.pop(index)

    def _require(self, task_id: str) -> tuple[int, EdgeExecutionTask]:
        for index, task in enumerate(self._tasks):
            if task.task_id == task_id:
                return index, task
        raise ValueError("A tarefa Edge não foi encontrada.")

    def _save(self) -> None:
        self._store.save(tuple(self._tasks))

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("O relógio da fila deve possuir fuso horário.")
        return value.astimezone(timezone.utc)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("A tarefa persistida deve ser um objeto.")
    return value


def _datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} é inválido.") from exc
    _require_aware(parsed, field_name)
    return parsed.astimezone(timezone.utc)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} deve possuir fuso horário.")


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} deve ser um inteiro não negativo.")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("O campo opcional persistido é inválido.")
    return value


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
