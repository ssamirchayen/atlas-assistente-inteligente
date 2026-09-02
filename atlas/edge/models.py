"""Safe local contracts for the Sprint 23 Atlas Edge agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
from typing import Any


_DEVICE_ID = re.compile(r"^edge_[a-f0-9]{32}$")
_ORGANIZATION_ID = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")


class EdgeDeviceStatus(StrEnum):
    """Operational states that can be exposed without private data."""

    UNENROLLED = "unenrolled"
    ONLINE = "online"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    """Random local identity; never derived from serial or hostname."""

    device_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not _DEVICE_ID.fullmatch(self.device_id):
            raise ValueError("O identificador do Atlas Edge é inválido.")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class DeviceEnrollment:
    """Approved organization binding without storing the approver name."""

    organization_id: str
    inventory_fingerprint: str
    approver_hash: str
    enrolled_at: datetime

    def __post_init__(self) -> None:
        organization_id = normalize_organization_id(self.organization_id)
        _require_digest(self.inventory_fingerprint, "inventory_fingerprint")
        _require_digest(self.approver_hash, "approver_hash")
        _require_aware(self.enrolled_at, "enrolled_at")
        object.__setattr__(self, "organization_id", organization_id)


@dataclass(frozen=True, slots=True)
class EdgePersistentState:
    """Small restart-safe state stored only on the managed computer."""

    identity: DeviceIdentity
    enrollment: DeviceEnrollment | None = None
    heartbeat_sequence: int = 0
    last_heartbeat_at: datetime | None = None
    paused: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("A versão do estado Atlas Edge não é suportada.")
        if self.heartbeat_sequence < 0:
            raise ValueError("A sequência de heartbeat não pode ser negativa.")
        if self.last_heartbeat_at is not None:
            _require_aware(self.last_heartbeat_at, "last_heartbeat_at")
        if self.enrollment is None and (
            self.heartbeat_sequence or self.last_heartbeat_at or self.paused
        ):
            raise ValueError("Um dispositivo não cadastrado não possui operação.")

    @property
    def status(self) -> EdgeDeviceStatus:
        if self.enrollment is None:
            return EdgeDeviceStatus.UNENROLLED
        return EdgeDeviceStatus.PAUSED if self.paused else EdgeDeviceStatus.ONLINE

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["identity"]["created_at"] = _iso(self.identity.created_at)
        if self.enrollment is not None:
            payload["enrollment"]["enrolled_at"] = _iso(
                self.enrollment.enrolled_at
            )
        if self.last_heartbeat_at is not None:
            payload["last_heartbeat_at"] = _iso(self.last_heartbeat_at)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EdgePersistentState":
        identity_payload = _dict(payload.get("identity"), "identity")
        enrollment_payload = payload.get("enrollment")
        enrollment = None
        if enrollment_payload is not None:
            item = _dict(enrollment_payload, "enrollment")
            enrollment = DeviceEnrollment(
                organization_id=str(item.get("organization_id", "")),
                inventory_fingerprint=str(
                    item.get("inventory_fingerprint", "")
                ),
                approver_hash=str(item.get("approver_hash", "")),
                enrolled_at=_datetime(item.get("enrolled_at"), "enrolled_at"),
            )

        last_heartbeat = payload.get("last_heartbeat_at")
        return cls(
            identity=DeviceIdentity(
                device_id=str(identity_payload.get("device_id", "")),
                created_at=_datetime(
                    identity_payload.get("created_at"),
                    "created_at",
                ),
            ),
            enrollment=enrollment,
            heartbeat_sequence=int(payload.get("heartbeat_sequence", 0)),
            last_heartbeat_at=(
                _datetime(last_heartbeat, "last_heartbeat_at")
                if last_heartbeat is not None
                else None
            ),
            paused=bool(payload.get("paused", False)),
            schema_version=int(payload.get("schema_version", 0)),
        )


@dataclass(frozen=True, slots=True)
class EnrollmentChallenge:
    """Short-lived, in-memory approval challenge."""

    token: str
    device_id: str
    organization_id: str
    inventory_fingerprint: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", self.token):
            raise ValueError("O token de cadastro é inválido.")
        if not _DEVICE_ID.fullmatch(self.device_id):
            raise ValueError("O dispositivo do cadastro é inválido.")
        object.__setattr__(
            self,
            "organization_id",
            normalize_organization_id(self.organization_id),
        )
        _require_digest(self.inventory_fingerprint, "inventory_fingerprint")
        _require_aware(self.expires_at, "expires_at")


@dataclass(frozen=True, slots=True)
class EdgeHeartbeat:
    """Sanitized status payload; it is not transmitted by Stage 1."""

    device_id: str
    organization_id: str
    sequence: int
    status: EdgeDeviceStatus
    agent_version: str
    inventory_fingerprint: str
    os_name: str
    os_version: str
    architecture: str
    winget_available: bool
    captured_at: datetime

    def __post_init__(self) -> None:
        if not _DEVICE_ID.fullmatch(self.device_id):
            raise ValueError("O dispositivo do heartbeat é inválido.")
        object.__setattr__(
            self,
            "organization_id",
            normalize_organization_id(self.organization_id),
        )
        if self.sequence <= 0:
            raise ValueError("A sequência do heartbeat deve ser positiva.")
        if not isinstance(self.status, EdgeDeviceStatus):
            raise TypeError("status deve ser EdgeDeviceStatus.")
        if not self.agent_version.strip():
            raise ValueError("A versão do agente é obrigatória.")
        _require_digest(self.inventory_fingerprint, "inventory_fingerprint")
        if not all(
            value.strip()
            for value in (self.os_name, self.os_version, self.architecture)
        ):
            raise ValueError("O inventário do heartbeat está incompleto.")
        _require_aware(self.captured_at, "captured_at")

    def as_payload(self) -> dict[str, object]:
        return {
            "device_id": self.device_id,
            "organization_id": self.organization_id,
            "sequence": self.sequence,
            "status": self.status.value,
            "agent_version": self.agent_version,
            "inventory_fingerprint": self.inventory_fingerprint,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "winget_available": self.winget_available,
            "captured_at": _iso(self.captured_at),
        }


def normalize_organization_id(value: str) -> str:
    normalized = str(value).strip().casefold()
    if not _ORGANIZATION_ID.fullmatch(normalized):
        raise ValueError("O identificador da organização é inválido.")
    return normalized


def _require_digest(value: str, field_name: str) -> None:
    if not _HEX_DIGEST.fullmatch(str(value)):
        raise ValueError(f"{field_name} deve ser um SHA-256.")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} deve possuir fuso horário.")


def _datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} é inválido.") from exc
    _require_aware(parsed, field_name)
    return parsed.astimezone(timezone.utc)


def _dict(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} deve ser um objeto.")
    return value


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
