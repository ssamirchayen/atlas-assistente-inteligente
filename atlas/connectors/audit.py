"""Auditoria sem conteúdo privado para decisões de conectores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from threading import Lock
from typing import Protocol
from uuid import uuid4

from atlas.connectors.models import (
    ConnectorAuthorization,
    ConnectorDecision,
    ConnectorOperation,
    ConnectorPrincipal,
    ConnectorRisk,
)


@dataclass(frozen=True, slots=True)
class ConnectorAuditRecord:
    """Evento seguro: não armazena parâmetros nem tokens de confirmação."""

    event_id: str
    occurred_at: datetime
    operation_id: str
    connector_id: str
    capability: str
    principal_id: str
    role: str
    risk: ConnectorRisk | None
    decision: ConnectorDecision
    reason: str
    batch_size: int
    idempotency_fingerprint: str | None


class ConnectorAuditTrail(Protocol):
    """Destino substituível para a trilha de integração."""

    def record(
        self,
        operation: ConnectorOperation,
        principal: ConnectorPrincipal,
        authorization: ConnectorAuthorization,
    ) -> ConnectorAuditRecord: ...

    def list_records(
        self,
        *,
        limit: int,
        connector_id: str | None = None,
        principal_id: str | None = None,
    ) -> tuple[ConnectorAuditRecord, ...]: ...


class NullConnectorAuditTrail:
    """Implementação sem persistência para composições mínimas."""

    def record(
        self,
        operation: ConnectorOperation,
        principal: ConnectorPrincipal,
        authorization: ConnectorAuthorization,
    ) -> ConnectorAuditRecord:
        return _new_record(operation, principal, authorization)

    def list_records(
        self,
        *,
        limit: int,
        connector_id: str | None = None,
        principal_id: str | None = None,
    ) -> tuple[ConnectorAuditRecord, ...]:
        del limit, connector_id, principal_id
        return ()


class InMemoryConnectorAuditTrail:
    """Trilha observável e thread-safe para testes e desenvolvimento."""

    def __init__(self) -> None:
        self._records: list[ConnectorAuditRecord] = []
        self._lock = Lock()

    def record(
        self,
        operation: ConnectorOperation,
        principal: ConnectorPrincipal,
        authorization: ConnectorAuthorization,
    ) -> ConnectorAuditRecord:
        record = _new_record(operation, principal, authorization)

        with self._lock:
            self._records.append(record)

        return record

    def list_records(
        self,
        *,
        limit: int,
        connector_id: str | None = None,
        principal_id: str | None = None,
    ) -> tuple[ConnectorAuditRecord, ...]:
        if limit <= 0:
            raise ValueError("O limite deve ser positivo.")

        normalized_connector = (
            connector_id.strip().lower() if connector_id else None
        )

        with self._lock:
            filtered = (
                record
                for record in reversed(self._records)
                if (
                    normalized_connector is None
                    or record.connector_id == normalized_connector
                )
                and (
                    principal_id is None
                    or record.principal_id == principal_id
                )
            )
            return tuple(list(filtered)[:limit])


def _new_record(
    operation: ConnectorOperation,
    principal: ConnectorPrincipal,
    authorization: ConnectorAuthorization,
) -> ConnectorAuditRecord:
    idempotency_fingerprint = (
        sha256(operation.idempotency_key.encode("utf-8")).hexdigest()
        if operation.idempotency_key
        else None
    )
    return ConnectorAuditRecord(
        event_id=uuid4().hex,
        occurred_at=authorization.decided_at,
        operation_id=operation.operation_id,
        connector_id=operation.connector_id,
        capability=operation.capability,
        principal_id=principal.principal_id,
        role=principal.role,
        risk=authorization.risk,
        decision=authorization.decision,
        reason=authorization.reason[:500],
        batch_size=operation.batch_size,
        idempotency_fingerprint=idempotency_fingerprint,
    )
