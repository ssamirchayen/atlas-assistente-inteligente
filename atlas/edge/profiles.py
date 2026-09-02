"""Declarative employee profiles and safe Atlas Edge plan contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4

from atlas.provisioning.models import ProvisioningPlan, ProvisioningProfile


_EDGE_PLAN_ID = re.compile(r"^edgeplan_[a-f0-9]{32}$")
_EDGE_AUTHORIZATION_ID = re.compile(r"^edgeauth_[a-f0-9]{32}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class EmployeeProfileSummary:
    """Public catalog entry without scripts, credentials or personal data."""

    profile_id: str
    display_name: str
    package_count: int
    directory_count: int
    profile_digest: str
    setting_count: int = 0

    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.display_name.strip():
            raise ValueError("O resumo do perfil está incompleto.")
        if (
            self.package_count < 0
            or self.directory_count < 0
            or self.setting_count < 0
        ):
            raise ValueError("As quantidades do perfil não podem ser negativas.")
        _require_digest(self.profile_digest, "profile_digest")


class EmployeeProfileCatalog:
    """Immutable allowlist of profiles selected by corporate IT."""

    def __init__(
        self,
        profiles: tuple[ProvisioningProfile, ...],
        *,
        max_profiles: int = 32,
        max_requirements_per_profile: int = 25,
    ) -> None:
        if max_profiles <= 0 or max_requirements_per_profile <= 0:
            raise ValueError("Os limites do catálogo devem ser positivos.")
        items = tuple(profiles)
        if not items:
            raise ValueError("Ao menos um perfil de funcionário é obrigatório.")
        if len(items) > max_profiles:
            raise ValueError("O catálogo excede o limite de perfis.")
        profile_map = {item.profile_id: item for item in items}
        if len(profile_map) != len(items):
            raise ValueError("Os perfis de funcionário devem possuir IDs únicos.")
        if any(
            len(item.packages) + len(item.directories) + len(item.settings)
            > max_requirements_per_profile
            for item in items
        ):
            raise ValueError("Um perfil excede o limite de requisitos.")
        self._profiles: Mapping[str, ProvisioningProfile] = MappingProxyType(
            profile_map
        )

    def get(self, profile_id: str) -> ProvisioningProfile:
        normalized = str(profile_id).strip().casefold()
        profile = self._profiles.get(normalized)
        if profile is None:
            raise ValueError("Perfil de funcionário não autorizado.")
        return profile

    def list(self) -> tuple[EmployeeProfileSummary, ...]:
        return tuple(
            EmployeeProfileSummary(
                profile_id=profile.profile_id,
                display_name=profile.display_name,
                package_count=len(profile.packages),
                directory_count=len(profile.directories),
                profile_digest=profile_digest(profile),
                setting_count=len(profile.settings),
            )
            for profile in sorted(
                self._profiles.values(),
                key=lambda item: item.profile_id,
            )
        )


@dataclass(frozen=True, slots=True)
class EdgeConfigurationPreview:
    """Human-readable configuration plan bound to one device and employee."""

    device_id: str
    organization_id: str
    profile_name: str
    profile_digest: str
    employee_reference_hash: str
    requester_hash: str
    plan: ProvisioningPlan
    expires_at: datetime
    request_id: str = field(default_factory=lambda: f"edgeplan_{uuid4().hex}")
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if not _EDGE_PLAN_ID.fullmatch(self.request_id):
            raise ValueError("O identificador da solicitação é inválido.")
        if not self.device_id.startswith("edge_"):
            raise ValueError("O dispositivo do plano é inválido.")
        if not self.organization_id.strip() or not self.profile_name.strip():
            raise ValueError("A organização e o perfil são obrigatórios.")
        for field_name, value in (
            ("profile_digest", self.profile_digest),
            ("employee_reference_hash", self.employee_reference_hash),
            ("requester_hash", self.requester_hash),
        ):
            _require_digest(value, field_name)
        _require_aware(self.created_at, "created_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("A autorização do plano deve expirar no futuro.")

    def as_payload(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "device_id": self.device_id,
            "organization_id": self.organization_id,
            "profile_id": self.plan.profile_id,
            "profile_name": self.profile_name,
            "profile_digest": self.profile_digest,
            "employee_reference_hash": self.employee_reference_hash,
            "requester_hash": self.requester_hash,
            "plan_digest": self.plan.digest(),
            "steps": [step.as_dict() for step in self.plan.steps],
            "created_at": _iso(self.created_at),
            "expires_at": _iso(self.expires_at),
        }


@dataclass(frozen=True, slots=True)
class EdgePlanChallenge:
    """Single-use approval token kept in memory by the service."""

    token: str
    preview: EdgeConfigurationPreview

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{12,64}", self.token):
            raise ValueError("O token do plano é inválido.")


@dataclass(frozen=True, slots=True)
class AuthorizedEdgePlan:
    """Approved plan receipt; Stage 2 never executes its steps."""

    preview: EdgeConfigurationPreview
    approver_hash: str
    authorized_at: datetime
    valid_until: datetime
    authorization_id: str = field(
        default_factory=lambda: f"edgeauth_{uuid4().hex}"
    )

    def __post_init__(self) -> None:
        if not _EDGE_AUTHORIZATION_ID.fullmatch(self.authorization_id):
            raise ValueError("O identificador da autorização é inválido.")
        _require_digest(self.approver_hash, "approver_hash")
        _require_aware(self.authorized_at, "authorized_at")
        _require_aware(self.valid_until, "valid_until")
        if self.valid_until <= self.authorized_at:
            raise ValueError("A autorização deve possuir validade futura.")

    def as_payload(self) -> dict[str, object]:
        return {
            "authorization_id": self.authorization_id,
            "status": "authorized",
            "approver_hash": self.approver_hash,
            "authorized_at": _iso(self.authorized_at),
            "valid_until": _iso(self.valid_until),
            "configuration": self.preview.as_payload(),
        }


def profile_digest(profile: ProvisioningProfile) -> str:
    payload = {
        "profile_id": profile.profile_id,
        "display_name": profile.display_name,
        "packages": [
            {
                "package_id": item.package_id,
                "display_name": item.display_name,
                "source": item.source,
            }
            for item in profile.packages
        ],
        "directories": [
            {
                "relative_path": item.relative_path,
                "description": item.description,
            }
            for item in profile.directories
        ],
        "settings": [item.as_dict() for item in profile.settings],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def hash_private_reference(value: str, field_name: str) -> str:
    normalized = str(value).strip().casefold()
    if not normalized or len(normalized) > 128:
        raise ValueError(f"{field_name} é inválido.")
    return sha256(normalized.encode("utf-8")).hexdigest()


def _require_digest(value: str, field_name: str) -> None:
    if not _HEX_DIGEST.fullmatch(str(value)):
        raise ValueError(f"{field_name} deve ser um SHA-256.")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} deve possuir fuso horário.")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
