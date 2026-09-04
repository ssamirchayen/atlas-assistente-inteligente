"""Modelos imutáveis para o inventário técnico de tratamento de dados."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_CONTROL_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class DataNature(StrEnum):
    """Natureza técnica; não substitui a qualificação jurídica do controlador."""

    NON_PERSONAL = "non_personal"
    PERSONAL = "personal"
    SENSITIVE_PERSONAL = "sensitive_personal"
    SECURITY_SECRET = "security_secret"


class DataCategory(StrEnum):
    IDENTIFICATION = "identification"
    CONTACT = "contact"
    CONVERSATION = "conversation"
    PREFERENCES = "preferences"
    VOICE_AUDIO = "voice_audio"
    SCREEN_IMAGE = "screen_image"
    HEALTH = "health"
    BIOMETRIC = "biometric"
    PROFESSIONAL = "professional"
    EDUCATIONAL = "educational"
    DEVICE_TECHNICAL = "device_technical"
    INTERNET_ACTIVITY = "internet_activity"
    AUTHENTICATION = "authentication"
    OPERATIONAL_AUDIT = "operational_audit"
    LOCATION = "location"
    FINANCIAL = "financial"


class DataSubject(StrEnum):
    USER = "user"
    EMPLOYEE = "employee"
    LEAD = "lead"
    SELLER = "seller"
    CUSTOMER = "customer"
    PATIENT = "patient"
    CHILD_OR_ADOLESCENT = "child_or_adolescent"
    OPERATOR = "operator"
    THIRD_PARTY = "third_party"


class ProcessingOperation(StrEnum):
    COLLECT = "collect"
    ACCESS = "access"
    USE = "use"
    STORE = "store"
    CLASSIFY = "classify"
    TRANSMIT = "transmit"
    SHARE = "share"
    PSEUDONYMIZE = "pseudonymize"
    DELETE = "delete"


class StorageKind(StrEnum):
    VOLATILE_MEMORY = "volatile_memory"
    SQLITE = "sqlite"
    JSON = "json"
    LOG = "log"
    MEDIA_FILE = "media_file"
    REMOTE_SERVICE = "remote_service"


class RetentionMode(StrEnum):
    TRANSIENT = "transient"
    CONFIGURED = "configured"
    BOUNDED_BY_COUNT = "bounded_by_count"
    EXTERNAL_POLICY = "external_policy"
    UNDEFINED = "undefined"


class LegalBasisStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    REQUIRES_CONTROLLER_DEFINITION = "requires_controller_definition"
    CONFIRMED_BY_CONTROLLER = "confirmed_by_controller"


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class DataStore:
    """Destino técnico sem incluir dados, tokens ou valores reais."""

    location: str
    kind: StorageKind
    provider: str
    local: bool
    encrypted_at_rest: bool | None
    ephemeral: bool = False

    def __post_init__(self) -> None:
        if not self.location.strip():
            raise ValueError("A localização do armazenamento é obrigatória.")
        if not self.provider.strip():
            raise ValueError("O provedor do armazenamento é obrigatório.")
        if not isinstance(self.kind, StorageKind):
            raise TypeError("kind deve ser StorageKind.")
        if self.ephemeral and self.kind not in {
            StorageKind.VOLATILE_MEMORY,
            StorageKind.MEDIA_FILE,
            StorageKind.REMOTE_SERVICE,
        }:
            raise ValueError("O tipo informado não admite estado transitório.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "kind": self.kind.value,
            "provider": self.provider,
            "local": self.local,
            "encrypted_at_rest": self.encrypted_at_rest,
            "ephemeral": self.ephemeral,
        }


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    mode: RetentionMode
    description: str
    configuration_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, RetentionMode):
            raise TypeError("mode deve ser RetentionMode.")
        if not self.description.strip():
            raise ValueError("A regra de retenção deve possuir descrição.")
        if self.mode is RetentionMode.CONFIGURED and not self.configuration_key:
            raise ValueError("A retenção configurada deve indicar sua chave.")
        if self.configuration_key and not re.fullmatch(
            r"ATLAS_[A-Z0-9_]{2,80}", self.configuration_key
        ):
            raise ValueError("A chave de retenção é inválida.")

    def as_dict(self) -> dict[str, str | None]:
        return {
            "mode": self.mode.value,
            "description": self.description,
            "configuration_key": self.configuration_key,
        }


@dataclass(frozen=True, slots=True)
class ProcessingRecord:
    """Registro de atividade de tratamento sem conteúdo pessoal real."""

    record_id: str
    name: str
    component: str
    nature: DataNature
    categories: tuple[DataCategory, ...]
    subjects: tuple[DataSubject, ...]
    operations: tuple[ProcessingOperation, ...]
    purpose: str
    source: str
    recipients: tuple[str, ...]
    stores: tuple[DataStore, ...]
    retention: RetentionPolicy
    controller_role: str
    operator_roles: tuple[str, ...]
    legal_basis_status: LegalBasisStatus
    legal_basis_reference: str | None = None
    international_transfer: bool = False
    automated_decision: bool = False
    implemented_controls: tuple[str, ...] = ()
    required_controls: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.record_id):
            raise ValueError("record_id deve ser um identificador técnico seguro.")
        for label, value in {
            "name": self.name,
            "component": self.component,
            "purpose": self.purpose,
            "source": self.source,
            "controller_role": self.controller_role,
        }.items():
            if not value.strip():
                raise ValueError(f"{label} não pode ser vazio.")
        if not isinstance(self.nature, DataNature):
            raise TypeError("nature deve ser DataNature.")
        if not self.categories:
            raise ValueError("O registro deve possuir categorias de dados.")
        if not self.operations:
            raise ValueError("O registro deve possuir operações de tratamento.")
        if self.nature is not DataNature.NON_PERSONAL and not self.subjects:
            raise ValueError("Dados pessoais devem indicar seus titulares.")
        if not self.recipients:
            raise ValueError("O registro deve indicar ao menos um destinatário.")
        if not self.stores:
            raise ValueError("O registro deve indicar ao menos um armazenamento.")
        if not isinstance(self.retention, RetentionPolicy):
            raise TypeError("retention deve ser RetentionPolicy.")
        if not isinstance(self.legal_basis_status, LegalBasisStatus):
            raise TypeError("legal_basis_status deve ser LegalBasisStatus.")
        if (
            self.legal_basis_status is LegalBasisStatus.CONFIRMED_BY_CONTROLLER
            and not self.legal_basis_reference
        ):
            raise ValueError("A base confirmada deve possuir referência.")
        if (
            self.legal_basis_status is LegalBasisStatus.NOT_APPLICABLE
            and self.nature is not DataNature.NON_PERSONAL
        ):
            raise ValueError("Dados pessoais exigem avaliação de base legal.")
        self._validate_unique("categories", self.categories)
        self._validate_unique("subjects", self.subjects)
        self._validate_unique("operations", self.operations)
        self._validate_unique("recipients", self.recipients)
        self._validate_controls(self.implemented_controls)
        self._validate_controls(self.required_controls)

    @staticmethod
    def _validate_unique(label: str, values: tuple[object, ...]) -> None:
        if len(values) != len(set(values)):
            raise ValueError(f"{label} não pode conter duplicidades.")

    @staticmethod
    def _validate_controls(values: tuple[str, ...]) -> None:
        if len(values) != len(set(values)):
            raise ValueError("Os controles não podem conter duplicidades.")
        if any(not _CONTROL_IDENTIFIER.fullmatch(value) for value in values):
            raise ValueError("Foi informado um identificador de controle inválido.")

    @property
    def unresolved_controls(self) -> tuple[str, ...]:
        implemented = set(self.implemented_controls)
        return tuple(
            control
            for control in self.required_controls
            if control not in implemented
        )

    @property
    def risk_level(self) -> RiskLevel:
        has_child = DataSubject.CHILD_OR_ADOLESCENT in self.subjects
        if (
            self.nature is DataNature.SENSITIVE_PERSONAL
            and (has_child or self.international_transfer)
        ):
            return RiskLevel.CRITICAL
        if (
            self.nature in {
                DataNature.SENSITIVE_PERSONAL,
                DataNature.SECURITY_SECRET,
            }
            or has_child
            or self.international_transfer
            or self.automated_decision
        ):
            return RiskLevel.HIGH
        if self.nature is DataNature.PERSONAL:
            return RiskLevel.MODERATE
        return RiskLevel.LOW

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "name": self.name,
            "component": self.component,
            "nature": self.nature.value,
            "categories": [item.value for item in self.categories],
            "subjects": [item.value for item in self.subjects],
            "operations": [item.value for item in self.operations],
            "purpose": self.purpose,
            "source": self.source,
            "recipients": list(self.recipients),
            "stores": [store.as_dict() for store in self.stores],
            "retention": self.retention.as_dict(),
            "controller_role": self.controller_role,
            "operator_roles": list(self.operator_roles),
            "legal_basis_status": self.legal_basis_status.value,
            "legal_basis_reference": self.legal_basis_reference,
            "international_transfer": self.international_transfer,
            "automated_decision": self.automated_decision,
            "implemented_controls": list(self.implemented_controls),
            "required_controls": list(self.required_controls),
            "unresolved_controls": list(self.unresolved_controls),
            "risk_level": self.risk_level.value,
            "notes": self.notes,
        }
