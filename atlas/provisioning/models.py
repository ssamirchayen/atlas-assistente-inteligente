"""Contratos imutáveis do provisionamento de computadores."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_PACKAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,255}$")


class ProvisioningStepType(StrEnum):
    """Únicas alterações permitidas nesta etapa."""

    CREATE_DIRECTORY = "create_directory"
    INSTALL_WINGET_PACKAGE = "install_winget_package"


class StepExecutionStatus(StrEnum):
    """Resultado de uma etapa do plano."""

    SIMULATED = "simulated"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class ProvisioningStatus(StrEnum):
    """Resultado agregado de uma execução."""

    DRY_RUN = "dry_run"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True, slots=True)
class PackageRequirement:
    """Pacote WinGet referenciado por ID exato e fonte fixa."""

    package_id: str
    display_name: str
    source: str = "winget"

    def __post_init__(self) -> None:
        package_id = self.package_id.strip()
        display_name = self.display_name.strip()
        source = self.source.strip().lower()

        if not _PACKAGE_ID_PATTERN.fullmatch(package_id):
            raise ValueError("O ID do pacote WinGet é inválido.")
        if not display_name:
            raise ValueError("O nome de exibição do pacote é obrigatório.")
        if source not in {"winget", "msstore"}:
            raise ValueError("A fonte do pacote não está autorizada.")

        object.__setattr__(self, "package_id", package_id)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class DirectoryRequirement:
    """Pasta relativa ao workspace corporativo do funcionário."""

    relative_path: str
    description: str

    def __post_init__(self) -> None:
        normalized = self.relative_path.strip().replace("\\", "/")
        description = self.description.strip()
        parts = tuple(part for part in normalized.split("/") if part)

        if not parts or normalized.startswith(("/", "~")):
            raise ValueError("O caminho da pasta deve ser relativo.")
        if any(part in {".", ".."} for part in parts):
            raise ValueError("O caminho da pasta não pode escapar do workspace.")
        if any(":" in part or "\x00" in part for part in parts):
            raise ValueError("O caminho da pasta contém caracteres proibidos.")
        if not description:
            raise ValueError("A descrição da pasta é obrigatória.")

        object.__setattr__(self, "relative_path", "/".join(parts))
        object.__setattr__(self, "description", description)


@dataclass(frozen=True, slots=True)
class ProvisioningProfile:
    """Configuração declarativa; não aceita scripts ou comandos livres."""

    profile_id: str
    display_name: str
    packages: tuple[PackageRequirement, ...] = ()
    directories: tuple[DirectoryRequirement, ...] = ()

    def __post_init__(self) -> None:
        profile_id = _normalize_identifier(self.profile_id)
        display_name = self.display_name.strip()
        packages = tuple(self.packages)
        directories = tuple(self.directories)

        if not display_name:
            raise ValueError("O nome do perfil é obrigatório.")
        if not packages and not directories:
            raise ValueError("O perfil deve possuir ao menos um requisito.")
        if len({item.package_id for item in packages}) != len(packages):
            raise ValueError("Os pacotes do perfil devem ser únicos.")
        if len({item.relative_path for item in directories}) != len(
            directories
        ):
            raise ValueError("As pastas do perfil devem ser únicas.")

        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "packages", packages)
        object.__setattr__(self, "directories", directories)


@dataclass(frozen=True, slots=True)
class DeviceInventory:
    """Inventário sem nome de usuário, serial ou hostname em texto aberto."""

    os_name: str
    os_version: str
    architecture: str
    device_hash: str
    winget_available: bool
    installed_package_ids: frozenset[str] = frozenset()
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        os_name = self.os_name.strip()
        os_version = self.os_version.strip()
        architecture = self.architecture.strip()
        installed = frozenset(
            package.strip() for package in self.installed_package_ids
        )

        if not os_name or not os_version or not architecture:
            raise ValueError("O inventário do sistema está incompleto.")
        if len(self.device_hash) != 64:
            raise ValueError("device_hash inválido.")
        if any(not _PACKAGE_ID_PATTERN.fullmatch(item) for item in installed):
            raise ValueError("O inventário contém pacote inválido.")
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at deve possuir fuso horário.")

        object.__setattr__(self, "os_name", os_name)
        object.__setattr__(self, "os_version", os_version)
        object.__setattr__(self, "architecture", architecture)
        object.__setattr__(self, "installed_package_ids", installed)
        object.__setattr__(
            self,
            "captured_at",
            self.captured_at.astimezone(timezone.utc),
        )

    def fingerprint(self) -> str:
        payload = {
            "os_name": self.os_name,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "device_hash": self.device_hash,
            "winget_available": self.winget_available,
            "installed": sorted(self.installed_package_ids),
        }
        return _hash_json(payload)


@dataclass(frozen=True, slots=True)
class ProvisioningStep:
    """Etapa gerada pelo planner, nunca recebida como comando arbitrário."""

    step_id: str
    step_type: ProvisioningStepType
    description: str
    parameters: Mapping[str, str]
    reversible: bool

    def __post_init__(self) -> None:
        step_id = _normalize_identifier(self.step_id)
        description = self.description.strip()
        parameters = {
            str(key).strip(): str(value).strip()
            for key, value in self.parameters.items()
        }

        if not isinstance(self.step_type, ProvisioningStepType):
            raise TypeError("step_type deve ser ProvisioningStepType.")
        if not description:
            raise ValueError("A descrição da etapa é obrigatória.")
        if not parameters or any(
            not key or not value for key, value in parameters.items()
        ):
            raise ValueError("Os parâmetros da etapa estão incompletos.")

        object.__setattr__(self, "step_id", step_id)
        object.__setattr__(self, "description", description)
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(parameters),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "description": self.description,
            "parameters": dict(self.parameters),
            "reversible": self.reversible,
        }


@dataclass(frozen=True, slots=True)
class ProvisioningPlan:
    """Plano vinculado ao perfil e ao inventário usados na aprovação."""

    profile_id: str
    inventory_fingerprint: str
    steps: tuple[ProvisioningStep, ...]
    plan_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        profile_id = _normalize_identifier(self.profile_id)
        plan_id = self.plan_id.strip()
        steps = tuple(self.steps)

        if not plan_id:
            raise ValueError("plan_id é obrigatório.")
        if len(self.inventory_fingerprint) != 64:
            raise ValueError("inventory_fingerprint inválido.")
        if not steps:
            raise ValueError("O plano não possui alterações necessárias.")
        if len({step.step_id for step in steps}) != len(steps):
            raise ValueError("Os IDs das etapas devem ser únicos.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at deve possuir fuso horário.")

        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "steps", steps)
        object.__setattr__(
            self,
            "created_at",
            self.created_at.astimezone(timezone.utc),
        )

    def digest(self) -> str:
        return _hash_json(
            {
                "plan_id": self.plan_id,
                "profile_id": self.profile_id,
                "inventory": self.inventory_fingerprint,
                "steps": [step.as_dict() for step in self.steps],
            }
        )


@dataclass(frozen=True, slots=True)
class ProvisioningApproval:
    """Plano exibido antes de qualquer alteração no computador."""

    plan: ProvisioningPlan
    summary: str
    reason: str
    confirmation_token: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StepEvidence:
    """Evidência sanitizada de uma etapa."""

    step_id: str
    status: StepExecutionStatus
    message: str
    duration_seconds: float

    def __post_init__(self) -> None:
        _normalize_identifier(self.step_id)
        if not isinstance(self.status, StepExecutionStatus):
            raise TypeError("status deve ser StepExecutionStatus.")
        if self.duration_seconds < 0:
            raise ValueError("A duração não pode ser negativa.")


@dataclass(frozen=True, slots=True)
class ProvisioningEvidence:
    """Resultado final sem credenciais, usuário ou hostname."""

    evidence_id: str
    plan_id: str
    plan_digest: str
    device_hash: str
    status: ProvisioningStatus
    steps: tuple[StepEvidence, ...]
    dry_run: bool
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.plan_id.strip():
            raise ValueError("Os identificadores da evidência são obrigatórios.")
        if len(self.plan_digest) != 64 or len(self.device_hash) != 64:
            raise ValueError("A evidência contém hashes inválidos.")
        if not isinstance(self.status, ProvisioningStatus):
            raise TypeError("status deve ser ProvisioningStatus.")
        if self.started_at.tzinfo is None or self.finished_at.tzinfo is None:
            raise ValueError("Os horários da evidência exigem fuso.")
        if self.finished_at < self.started_at:
            raise ValueError("A conclusão não pode preceder o início.")


def _normalize_identifier(value: str) -> str:
    normalized = value.strip().lower()

    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError("O identificador é inválido.")

    return normalized


def _hash_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
