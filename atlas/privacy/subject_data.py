"""Adaptadores explícitos de dados usados no atendimento aos titulares."""

from __future__ import annotations

from dataclasses import dataclass
import re
from threading import RLock
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from atlas.privacy.models import DataCategory
from atlas.privacy.policy import DeclaredLegalBasis


_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
_PSEUDONYM = re.compile(r"^psn_[a-f0-9]{64}$")


def _safe_identifiers(
    label: str,
    values: Iterable[str],
    *,
    required: bool = True,
) -> tuple[str, ...]:
    result = tuple(values)
    if required and not result:
        raise ValueError(f"{label} não pode ser vazio.")
    if len(result) != len(set(result)):
        raise ValueError(f"{label} não pode conter duplicidades.")
    if any(not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value) for value in result):
        raise ValueError(f"{label} contém identificador inválido.")
    return result


@dataclass(frozen=True, slots=True)
class DeletionPlan:
    source_id: str
    record_id: str
    record_count: int
    retention_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.source_id):
            raise ValueError("source_id é inválido.")
        if not _SAFE_IDENTIFIER.fullmatch(self.record_id):
            raise ValueError("record_id é inválido.")
        if self.record_count < 0:
            raise ValueError("record_count não pode ser negativo.")
        object.__setattr__(
            self,
            "retention_reasons",
            _safe_identifiers(
                "retention_reasons",
                self.retention_reasons,
                required=False,
            ),
        )

    @property
    def can_delete(self) -> bool:
        return not self.retention_reasons


@runtime_checkable
class SubjectDataSource(Protocol):
    source_id: str
    organization_id: str
    record_id: str
    categories: tuple[DataCategory, ...]
    fields: tuple[str, ...]
    legal_basis: DeclaredLegalBasis

    def has_subject(self, subject_pseudonym: str) -> bool: ...

    def read(
        self,
        subject_pseudonym: str,
        fields: tuple[str, ...],
    ) -> Mapping[str, Any]: ...

    def correct(
        self,
        subject_pseudonym: str,
        corrections: Mapping[str, Any],
    ) -> int: ...

    def plan_delete(self, subject_pseudonym: str) -> DeletionPlan: ...

    def delete(self, subject_pseudonym: str) -> int: ...


class InMemorySubjectDataSource:
    """Adaptador de laboratório; nunca é conectado automaticamente à produção."""

    def __init__(
        self,
        *,
        source_id: str,
        organization_id: str,
        record_id: str,
        categories: Iterable[DataCategory],
        fields: Iterable[str],
        legal_basis: DeclaredLegalBasis,
        retention_reasons: Iterable[str] = (),
    ) -> None:
        for label, value in {
            "source_id": source_id,
            "organization_id": organization_id,
            "record_id": record_id,
        }.items():
            if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
                raise ValueError(f"{label} é inválido.")
        category_tuple = tuple(categories)
        if not category_tuple or any(
            not isinstance(category, DataCategory) for category in category_tuple
        ):
            raise TypeError("categories deve conter DataCategory.")
        if len(category_tuple) != len(set(category_tuple)):
            raise ValueError("categories não pode conter duplicidades.")
        if not isinstance(legal_basis, DeclaredLegalBasis):
            raise TypeError("legal_basis deve ser DeclaredLegalBasis.")
        self.source_id = source_id
        self.organization_id = organization_id
        self.record_id = record_id
        self.categories = category_tuple
        self.fields = _safe_identifiers("fields", fields)
        self.legal_basis = legal_basis
        self._retention_reasons = _safe_identifiers(
            "retention_reasons",
            retention_reasons,
            required=False,
        )
        self._rows: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def put(self, subject_pseudonym: str, payload: Mapping[str, Any]) -> None:
        self._validate_subject(subject_pseudonym)
        if not isinstance(payload, Mapping):
            raise TypeError("payload deve ser mapeamento.")
        unknown = set(payload) - set(self.fields)
        if unknown:
            raise ValueError("payload contém campos não declarados.")
        with self._lock:
            self._rows[subject_pseudonym] = dict(payload)

    def has_subject(self, subject_pseudonym: str) -> bool:
        self._validate_subject(subject_pseudonym)
        with self._lock:
            return subject_pseudonym in self._rows

    def read(
        self,
        subject_pseudonym: str,
        fields: tuple[str, ...],
    ) -> Mapping[str, Any]:
        self._validate_subject(subject_pseudonym)
        selected = _safe_identifiers("fields", fields)
        if not set(selected).issubset(self.fields):
            raise ValueError("A leitura solicitou campos não declarados.")
        with self._lock:
            row = self._rows.get(subject_pseudonym, {})
            result = {field: row[field] for field in selected if field in row}
        return MappingProxyType(result)

    def correct(
        self,
        subject_pseudonym: str,
        corrections: Mapping[str, Any],
    ) -> int:
        self._validate_subject(subject_pseudonym)
        if not isinstance(corrections, Mapping) or not corrections:
            raise ValueError("corrections deve conter ao menos um campo.")
        fields = tuple(corrections)
        _safe_identifiers("corrections", fields)
        if not set(fields).issubset(self.fields):
            raise ValueError("A correção contém campos não declarados.")
        with self._lock:
            if subject_pseudonym not in self._rows:
                return 0
            changed = sum(
                self._rows[subject_pseudonym].get(field) != value
                for field, value in corrections.items()
            )
            self._rows[subject_pseudonym].update(corrections)
        return changed

    def plan_delete(self, subject_pseudonym: str) -> DeletionPlan:
        self._validate_subject(subject_pseudonym)
        with self._lock:
            count = int(subject_pseudonym in self._rows)
        return DeletionPlan(
            source_id=self.source_id,
            record_id=self.record_id,
            record_count=count,
            retention_reasons=self._retention_reasons,
        )

    def delete(self, subject_pseudonym: str) -> int:
        plan = self.plan_delete(subject_pseudonym)
        if not plan.can_delete:
            raise PermissionError("A fonte possui impedimento de retenção.")
        with self._lock:
            return int(self._rows.pop(subject_pseudonym, None) is not None)

    @staticmethod
    def _validate_subject(subject_pseudonym: str) -> None:
        if not isinstance(subject_pseudonym, str) or not _PSEUDONYM.fullmatch(
            subject_pseudonym
        ):
            raise ValueError("subject_pseudonym é inválido.")
