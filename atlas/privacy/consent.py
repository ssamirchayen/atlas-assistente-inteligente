"""Recibos de consentimento pseudônimos, revogáveis e com escopo estrito."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import re
from threading import RLock
from typing import Callable, Iterable
from uuid import uuid4

from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_PSEUDONYM = re.compile(r"^psn_[a-f0-9]{64}$")


def _utc(value: datetime, *, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} deve possuir fuso horário.")
    return value.astimezone(timezone.utc)


def digest_consent_evidence(evidence: str) -> str:
    normalized = evidence.strip() if isinstance(evidence, str) else ""
    if not normalized:
        raise ValueError("A evidência de consentimento não pode ser vazia.")
    return hashlib.sha256(normalized.encode()).hexdigest()


class ConsentStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ConsentReceipt:
    receipt_id: str
    organization_id: str
    subject_pseudonym: str
    record_id: str
    purpose: str
    categories: tuple[DataCategory, ...]
    evidence_digest: str
    granted_by_hash: str
    granted_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by_hash: str | None = None

    def __post_init__(self) -> None:
        for label, value in {
            "organization_id": self.organization_id,
            "record_id": self.record_id,
            "purpose": self.purpose,
        }.items():
            if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        if not isinstance(self.receipt_id, str) or not re.fullmatch(
            r"[a-f0-9]{32}", self.receipt_id
        ):
            raise ValueError("receipt_id é inválido.")
        if not isinstance(self.subject_pseudonym, str) or not _PSEUDONYM.fullmatch(
            self.subject_pseudonym
        ):
            raise ValueError("subject_pseudonym é inválido.")
        if not self.categories or any(
            not isinstance(category, DataCategory) for category in self.categories
        ):
            raise TypeError("categories deve conter DataCategory.")
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("categories não pode conter duplicidades.")
        for label, value in {
            "evidence_digest": self.evidence_digest,
            "granted_by_hash": self.granted_by_hash,
        }.items():
            if not isinstance(value, str) or not _HEX_DIGEST.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        granted_at = _utc(self.granted_at, label="granted_at")
        object.__setattr__(self, "granted_at", granted_at)
        if self.expires_at is not None:
            expires_at = _utc(self.expires_at, label="expires_at")
            if expires_at <= granted_at:
                raise ValueError("expires_at deve ser posterior a granted_at.")
            object.__setattr__(self, "expires_at", expires_at)
        if self.revoked_at is not None:
            revoked_at = _utc(self.revoked_at, label="revoked_at")
            if revoked_at < granted_at:
                raise ValueError("revoked_at não pode anteceder granted_at.")
            if not self.revoked_by_hash or not _HEX_DIGEST.fullmatch(
                self.revoked_by_hash
            ):
                raise ValueError("A revogação deve identificar o responsável.")
            object.__setattr__(self, "revoked_at", revoked_at)
        elif self.revoked_by_hash is not None:
            raise ValueError("revoked_by_hash exige revoked_at.")

    def status_at(self, moment: datetime) -> ConsentStatus:
        current = _utc(moment, label="moment")
        if self.revoked_at is not None and current >= self.revoked_at:
            return ConsentStatus.REVOKED
        if self.expires_at is not None and current >= self.expires_at:
            return ConsentStatus.EXPIRED
        return ConsentStatus.ACTIVE


class ConsentRegistry:
    """Registro em memória; persistência e direitos chegam nas próximas etapas."""

    def __init__(
        self,
        pseudonymizer: Pseudonymizer,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(pseudonymizer, Pseudonymizer):
            raise TypeError("pseudonymizer deve ser Pseudonymizer.")
        self._pseudonymizer = pseudonymizer
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._receipts: dict[str, ConsentReceipt] = {}
        self._lock = RLock()

    def grant(
        self,
        *,
        organization_id: str,
        subject_id: str,
        record_id: str,
        purpose: str,
        categories: Iterable[DataCategory],
        evidence: str,
        granted_by: str,
        expires_at: datetime | None = None,
    ) -> ConsentReceipt:
        now = _utc(self._clock(), label="clock")
        if expires_at is not None:
            expires_at = _utc(expires_at, label="expires_at")
        category_tuple = tuple(categories)
        receipt = ConsentReceipt(
            receipt_id=uuid4().hex,
            organization_id=organization_id,
            subject_pseudonym=self.subject_pseudonym(
                organization_id=organization_id,
                subject_id=subject_id,
            ),
            record_id=record_id,
            purpose=purpose,
            categories=category_tuple,
            evidence_digest=digest_consent_evidence(evidence),
            granted_by_hash=self._actor_hash(organization_id, granted_by),
            granted_at=now,
            expires_at=expires_at,
        )
        with self._lock:
            self._receipts[receipt.receipt_id] = receipt
        return receipt

    def revoke(
        self,
        receipt_id: str,
        *,
        organization_id: str,
        revoked_by: str,
    ) -> ConsentReceipt:
        now = _utc(self._clock(), label="clock")
        with self._lock:
            try:
                receipt = self._receipts[receipt_id]
            except KeyError as error:
                raise KeyError("Recibo de consentimento não encontrado.") from error
            if receipt.organization_id != organization_id:
                raise PermissionError("O recibo pertence a outra organização.")
            if receipt.revoked_at is not None:
                return receipt
            revoked = replace(
                receipt,
                revoked_at=now,
                revoked_by_hash=self._actor_hash(organization_id, revoked_by),
            )
            self._receipts[receipt_id] = revoked
            return revoked

    def find_valid(
        self,
        *,
        organization_id: str,
        subject_id: str,
        record_id: str,
        purpose: str,
        categories: Iterable[DataCategory],
        receipt_id: str | None = None,
    ) -> ConsentReceipt | None:
        subject = self.subject_pseudonym(
            organization_id=organization_id,
            subject_id=subject_id,
        )
        requested = set(categories)
        now = _utc(self._clock(), label="clock")
        with self._lock:
            candidates = tuple(self._receipts.values())
        candidates = tuple(
            receipt
            for receipt in candidates
            if receipt.organization_id == organization_id
            and receipt.subject_pseudonym == subject
            and receipt.record_id == record_id
            and receipt.purpose == purpose
            and (receipt_id is None or receipt.receipt_id == receipt_id)
            and requested.issubset(set(receipt.categories))
        )
        if not candidates:
            return None
        latest = max(
            enumerate(candidates),
            key=lambda item: (item[1].granted_at, item[0]),
        )[1]
        return latest if latest.status_at(now) is ConsentStatus.ACTIVE else None

    def list_for_subject(
        self,
        *,
        organization_id: str,
        subject_id: str,
    ) -> tuple[ConsentReceipt, ...]:
        subject = self.subject_pseudonym(
            organization_id=organization_id,
            subject_id=subject_id,
        )
        with self._lock:
            result = tuple(
                receipt
                for receipt in self._receipts.values()
                if receipt.organization_id == organization_id
                and receipt.subject_pseudonym == subject
            )
        return tuple(sorted(result, key=lambda item: (item.granted_at, item.receipt_id)))

    def subject_pseudonym(self, *, organization_id: str, subject_id: str) -> str:
        return self._pseudonymizer.pseudonymize(
            subject_id,
            namespace=f"consent:{organization_id}:subject",
        )

    def _actor_hash(self, organization_id: str, actor_id: str) -> str:
        pseudonym = self._pseudonymizer.pseudonymize(
            actor_id,
            namespace=f"consent:{organization_id}:actor",
        )
        return hashlib.sha256(pseudonym.encode()).hexdigest()
