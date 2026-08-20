"""Modelos seguros do piloto escolar da Sprint 22."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import re


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
_PHONE_NUMBER_ID_PATTERN = re.compile(r"^\d{5,32}$")
_TEMPLATE_PATTERN = re.compile(r"^[a-z0-9_]{1,512}$")
_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:_[A-Z]{2})?$")


class LeadStatus(StrEnum):
    """Situação operacional do lead no CRM escolar."""

    NEW = "new"
    ASSIGNED = "assigned"
    CONTACTED = "contacted"
    DO_NOT_CONTACT = "do_not_contact"


class OptInStatus(StrEnum):
    """Consentimento do titular para receber mensagens no WhatsApp."""

    UNKNOWN = "unknown"
    GRANTED = "granted"
    REVOKED = "revoked"


class DeliveryStatus(StrEnum):
    """Estado conhecido do envio ao provedor."""

    DRY_RUN = "dry_run"
    ACCEPTED = "accepted"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SchoolLead:
    """Lead mínimo; o telefone nunca deve aparecer em logs ou auditoria."""

    lead_id: str
    name: str
    phone_e164: str
    offering: str
    opt_in: OptInStatus = OptInStatus.UNKNOWN
    opt_in_at: datetime | None = None
    opt_in_source: str = ""
    status: LeadStatus = LeadStatus.NEW
    assigned_seller_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.lead_id, field_name="lead_id")
        name = self.name.strip()
        offering = self.offering.strip()
        phone = self.phone_e164.strip()
        source = self.opt_in_source.strip()
        seller_id = (
            self.assigned_seller_id.strip()
            if self.assigned_seller_id
            else None
        )

        if not name:
            raise ValueError("O nome do lead é obrigatório.")
        if not offering:
            raise ValueError("A oferta de interesse é obrigatória.")
        if not _E164_PATTERN.fullmatch(phone):
            raise ValueError("O telefone deve estar no formato E.164.")
        if not isinstance(self.opt_in, OptInStatus):
            raise TypeError("opt_in deve ser um OptInStatus.")
        if not isinstance(self.status, LeadStatus):
            raise TypeError("status deve ser um LeadStatus.")
        if self.opt_in_at is not None and self.opt_in_at.tzinfo is None:
            raise ValueError("opt_in_at deve possuir fuso horário.")
        if self.opt_in is OptInStatus.GRANTED:
            if self.opt_in_at is None or not source:
                raise ValueError(
                    "O opt-in concedido exige horário e origem da prova."
                )
        if seller_id is not None:
            _validate_identifier(seller_id, field_name="assigned_seller_id")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "offering", offering)
        object.__setattr__(self, "phone_e164", phone)
        object.__setattr__(self, "opt_in_source", source)
        object.__setattr__(self, "assigned_seller_id", seller_id)
        if self.opt_in_at is not None:
            object.__setattr__(
                self,
                "opt_in_at",
                self.opt_in_at.astimezone(timezone.utc),
            )

    @property
    def contact_allowed(self) -> bool:
        return (
            self.opt_in is OptInStatus.GRANTED
            and self.status is not LeadStatus.DO_NOT_CONTACT
        )

    @property
    def destination_hash(self) -> str:
        return sha256(self.phone_e164.encode("utf-8")).hexdigest()

    @property
    def masked_phone(self) -> str:
        return f"***{self.phone_e164[-4:]}"


@dataclass(frozen=True, slots=True)
class SchoolSeller:
    """Vendedor e número corporativo oficial associado na Meta."""

    seller_id: str
    name: str
    phone_number_id: str
    active: bool = True
    max_open_leads: int = 50

    def __post_init__(self) -> None:
        _validate_identifier(self.seller_id, field_name="seller_id")
        name = self.name.strip()
        phone_number_id = self.phone_number_id.strip()

        if not name:
            raise ValueError("O nome do vendedor é obrigatório.")
        if not _PHONE_NUMBER_ID_PATTERN.fullmatch(phone_number_id):
            raise ValueError("phone_number_id corporativo inválido.")
        if self.max_open_leads <= 0:
            raise ValueError("max_open_leads deve ser positivo.")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "phone_number_id", phone_number_id)


@dataclass(frozen=True, slots=True)
class ApprovedTemplate:
    """Template que precisa existir e estar aprovado na conta da escola."""

    name: str
    language_code: str = "pt_BR"
    parameter_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        name = self.name.strip().lower()
        language = self.language_code.strip()
        parameter_names = tuple(
            item.strip() for item in self.parameter_names
        )

        if not _TEMPLATE_PATTERN.fullmatch(name):
            raise ValueError("O nome do template oficial é inválido.")
        if not _LANGUAGE_PATTERN.fullmatch(language):
            raise ValueError("O código de idioma do template é inválido.")
        if any(not item for item in parameter_names):
            raise ValueError("Os nomes dos parâmetros não podem ser vazios.")
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError("Os parâmetros do template devem ser únicos.")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "language_code", language)
        object.__setattr__(self, "parameter_names", parameter_names)


@dataclass(frozen=True, slots=True)
class LeadSummary:
    """Visão sem telefone para filas e interfaces operacionais."""

    lead_id: str
    name: str
    offering: str
    status: LeadStatus
    opt_in: OptInStatus
    assigned_seller_id: str | None
    masked_phone: str

    @classmethod
    def from_lead(cls, lead: SchoolLead) -> LeadSummary:
        return cls(
            lead_id=lead.lead_id,
            name=lead.name,
            offering=lead.offering,
            status=lead.status,
            opt_in=lead.opt_in,
            assigned_seller_id=lead.assigned_seller_id,
            masked_phone=lead.masked_phone,
        )


@dataclass(frozen=True, slots=True)
class PendingApproval:
    """Resposta segura de uma operação que aguarda o operador."""

    operation_id: str
    summary: str
    allowed: bool
    reason: str
    confirmation_token: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MessageDelivery:
    """Evidência mínima de envio, sem armazenar o telefone do aluno."""

    delivery_id: str
    lead_id: str
    seller_id: str
    destination_hash: str
    template_name: str
    provider_message_id: str
    status: DeliveryStatus
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        _validate_identifier(self.delivery_id, field_name="delivery_id")
        _validate_identifier(self.lead_id, field_name="lead_id")
        _validate_identifier(self.seller_id, field_name="seller_id")

        if len(self.destination_hash) != 64:
            raise ValueError("destination_hash inválido.")
        if not self.provider_message_id.strip():
            raise ValueError("O identificador da mensagem é obrigatório.")
        if not isinstance(self.status, DeliveryStatus):
            raise TypeError("status deve ser um DeliveryStatus.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at deve possuir fuso horário.")

        object.__setattr__(
            self,
            "created_at",
            self.created_at.astimezone(timezone.utc),
        )


def _validate_identifier(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value.strip()):
        raise ValueError(f"{field_name} inválido.")
