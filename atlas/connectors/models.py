"""Contratos imutáveis da camada de conectores empresariais do Atlas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from math import isfinite
import re
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


class ConnectorRisk(StrEnum):
    """Impacto esperado de uma capacidade de integração."""

    READ_ONLY = "read_only"
    EXTERNAL_WRITE = "external_write"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"


class ConnectorDecision(StrEnum):
    """Decisão retornada antes de qualquer chamada a um sistema externo."""

    ALLOWED = "allowed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    DENIED = "denied"
    RATE_LIMITED = "rate_limited"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class ConnectorCapability:
    """Ação declarada por um conector, com escopo e risco fixos."""

    name: str
    required_scope: str
    risk: ConnectorRisk
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_identifier(self.name))
        scope = self.required_scope.strip().lower()

        if not scope:
            raise ValueError("O escopo da capacidade é obrigatório.")

        if not isinstance(self.risk, ConnectorRisk):
            raise TypeError("O risco deve ser um ConnectorRisk.")

        object.__setattr__(self, "required_scope", scope)
        object.__setattr__(self, "description", self.description.strip())


@dataclass(frozen=True, slots=True)
class ConnectorManifest:
    """Metadados e limites que um conector não pode alterar em execução."""

    connector_id: str
    display_name: str
    description: str
    capabilities: tuple[ConnectorCapability, ...]
    max_batch_size: int = 1
    operations_per_minute: int = 30
    enabled: bool = True
    allow_destructive: bool = False

    def __post_init__(self) -> None:
        connector_id = _normalize_identifier(self.connector_id)
        display_name = self.display_name.strip()
        description = self.description.strip()
        capabilities = tuple(self.capabilities)

        if not display_name:
            raise ValueError("O nome de exibição do conector é obrigatório.")

        if not description:
            raise ValueError("A descrição do conector é obrigatória.")

        if not capabilities:
            raise ValueError("O conector deve declarar ao menos uma capacidade.")

        names = [capability.name for capability in capabilities]

        if len(names) != len(set(names)):
            raise ValueError("As capacidades do conector devem ser únicas.")

        if self.max_batch_size <= 0:
            raise ValueError("O limite de lote deve ser positivo.")

        if self.operations_per_minute <= 0:
            raise ValueError("O limite por minuto deve ser positivo.")

        object.__setattr__(self, "connector_id", connector_id)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "capabilities", capabilities)

    def get_capability(self, name: str) -> ConnectorCapability | None:
        normalized_name = _normalize_identifier(name)
        return next(
            (
                capability
                for capability in self.capabilities
                if capability.name == normalized_name
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class ConnectorPrincipal:
    """Identidade e permissões de quem solicitou uma integração."""

    principal_id: str
    role: str
    scopes: frozenset[str]

    def __post_init__(self) -> None:
        principal_id = self.principal_id.strip()
        role = self.role.strip().lower()
        scopes = frozenset(
            scope.strip().lower()
            for scope in self.scopes
            if scope and scope.strip()
        )

        if not principal_id:
            raise ValueError("O identificador do solicitante é obrigatório.")

        if not role:
            raise ValueError("O papel do solicitante é obrigatório.")

        object.__setattr__(self, "principal_id", principal_id)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "scopes", scopes)

    def has_scope(self, required_scope: str) -> bool:
        scope = required_scope.strip().lower()
        return "*" in self.scopes or scope in self.scopes


@dataclass(frozen=True, slots=True)
class ConnectorOperation:
    """Solicitação de integração ainda não autorizada nem executada."""

    connector_id: str
    capability: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    batch_size: int = 1
    idempotency_key: str | None = None
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        connector_id = _normalize_identifier(self.connector_id)
        capability = _normalize_identifier(self.capability)
        operation_id = self.operation_id.strip()
        idempotency_key = (
            self.idempotency_key.strip() if self.idempotency_key else None
        )

        if not operation_id:
            raise ValueError("O identificador da operação é obrigatório.")

        if self.batch_size <= 0:
            raise ValueError("O tamanho do lote deve ser positivo.")

        if self.created_at.tzinfo is None:
            raise ValueError("created_at deve possuir fuso horário.")

        frozen_parameters = _freeze_mapping(self.parameters)
        object.__setattr__(self, "connector_id", connector_id)
        object.__setattr__(self, "capability", capability)
        object.__setattr__(self, "parameters", frozen_parameters)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "idempotency_key", idempotency_key)
        object.__setattr__(
            self,
            "created_at",
            self.created_at.astimezone(timezone.utc),
        )

    def fingerprint(self) -> str:
        """Vincula uma confirmação ao conteúdo exato da operação."""

        canonical = json.dumps(
            {
                "operation_id": self.operation_id,
                "connector_id": self.connector_id,
                "capability": self.capability,
                "parameters": _thaw_value(self.parameters),
                "batch_size": self.batch_size,
                "idempotency_key": self.idempotency_key,
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConnectorAuthorization:
    """Resultado auditável da avaliação de uma operação."""

    operation_id: str
    decision: ConnectorDecision
    reason: str
    decided_at: datetime
    risk: ConnectorRisk | None = None
    confirmation_token: str | None = None
    confirmation_expires_at: datetime | None = None
    retry_after_seconds: float | None = None

    @property
    def allowed(self) -> bool:
        return self.decision is ConnectorDecision.ALLOWED

    @property
    def requires_confirmation(self) -> bool:
        return self.decision is ConnectorDecision.CONFIRMATION_REQUIRED


def _normalize_identifier(value: str) -> str:
    normalized = value.strip().lower()

    if not normalized or not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            "O identificador deve começar com letra e conter apenas "
            "letras minúsculas, números, ponto, hífen ou sublinhado."
        )

    return normalized


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("Os parâmetros devem ser um mapeamento.")

    frozen: dict[str, object] = {}

    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise TypeError("As chaves dos parâmetros devem ser textos.")

        frozen[key] = _freeze_value(item)

    return MappingProxyType(frozen)


def _freeze_value(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value

    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("Os parâmetros não aceitam números não finitos.")
        return value

    if isinstance(value, Mapping):
        return _freeze_mapping(value)

    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)

    raise TypeError("Os parâmetros devem conter apenas valores JSON.")


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}

    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]

    return value
