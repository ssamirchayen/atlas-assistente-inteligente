"""Autorização central antes de integrações com sistemas externos."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
from threading import RLock

from atlas.connectors.audit import (
    ConnectorAuditTrail,
    NullConnectorAuditTrail,
)
from atlas.connectors.models import (
    ConnectorAuthorization,
    ConnectorDecision,
    ConnectorOperation,
    ConnectorPrincipal,
    ConnectorRisk,
)
from atlas.connectors.registry import ConnectorRegistry


_CONFIRMATION_RISKS = frozenset(
    {
        ConnectorRisk.EXTERNAL_WRITE,
        ConnectorRisk.SENSITIVE,
        ConnectorRisk.DESTRUCTIVE,
    }
)
_IDEMPOTENCY_RISKS = frozenset(
    {
        ConnectorRisk.EXTERNAL_WRITE,
        ConnectorRisk.DESTRUCTIVE,
    }
)


@dataclass(frozen=True, slots=True)
class _PendingConfirmation:
    operation_fingerprint: str
    principal_id: str
    expires_at: datetime


class ConnectorGuard:
    """Aplica escopo, confirmação, lote, limite e idempotência."""

    def __init__(
        self,
        registry: ConnectorRegistry,
        *,
        audit: ConnectorAuditTrail | None = None,
        confirmation_ttl_seconds: float = 300.0,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if confirmation_ttl_seconds <= 0:
            raise ValueError("A validade da confirmação deve ser positiva.")

        self._registry = registry
        self._audit = audit or NullConnectorAuditTrail()
        self._confirmation_ttl = timedelta(
            seconds=confirmation_ttl_seconds
        )
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or (
            lambda: secrets.token_urlsafe(24)
        )
        self._pending: dict[str, _PendingConfirmation] = {}
        self._usage: dict[
            tuple[str, str], deque[tuple[datetime, int]]
        ] = {}
        self._reserved_idempotency_keys: set[tuple[str, str]] = set()
        self._lock = RLock()

    def authorize(
        self,
        operation: ConnectorOperation,
        principal: ConnectorPrincipal,
        *,
        confirmation_token: str | None = None,
    ) -> ConnectorAuthorization:
        """Avalia uma operação sem realizar a chamada externa."""

        if not isinstance(operation, ConnectorOperation):
            raise TypeError("operation deve ser uma ConnectorOperation.")

        if not isinstance(principal, ConnectorPrincipal):
            raise TypeError("principal deve ser um ConnectorPrincipal.")

        with self._lock:
            now = self._now()
            self._prune_usage(now)
            self._prune_pending(now, preserve=confirmation_token)
            authorization = self._evaluate(
                operation,
                principal,
                confirmation_token=confirmation_token,
                now=now,
            )

        self._audit.record(operation, principal, authorization)
        return authorization

    def revoke_confirmation(self, token: str) -> bool:
        """Revoga uma aprovação pendente ainda não consumida."""

        with self._lock:
            return self._pending.pop(token, None) is not None

    def _evaluate(
        self,
        operation: ConnectorOperation,
        principal: ConnectorPrincipal,
        *,
        confirmation_token: str | None,
        now: datetime,
    ) -> ConnectorAuthorization:
        resolved = self._registry.resolve(
            operation.connector_id,
            operation.capability,
        )

        if resolved is None:
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "Conector ou capacidade não registrado.",
                now=now,
            )

        connector, capability = resolved
        risk = capability.risk

        if not connector.enabled:
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "O conector está desativado.",
                risk=risk,
                now=now,
            )

        if not principal.has_scope(capability.required_scope):
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                f"Escopo obrigatório ausente: {capability.required_scope}.",
                risk=risk,
                now=now,
            )

        if operation.batch_size > connector.max_batch_size:
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "O lote excede o limite permitido pelo conector.",
                risk=risk,
                now=now,
            )

        if risk is ConnectorRisk.DESTRUCTIVE and not connector.allow_destructive:
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "Operações destrutivas estão bloqueadas neste conector.",
                risk=risk,
                now=now,
            )

        if risk in _IDEMPOTENCY_RISKS and not operation.idempotency_key:
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "A operação exige uma chave de idempotência.",
                risk=risk,
                now=now,
            )

        idempotency_identity = self._idempotency_identity(operation)

        if (
            idempotency_identity is not None
            and idempotency_identity in self._reserved_idempotency_keys
        ):
            return self._result(
                operation,
                ConnectorDecision.DUPLICATE,
                "A chave de idempotência já foi autorizada.",
                risk=risk,
                now=now,
            )

        retry_after = self._retry_after(
            principal,
            operation,
            limit=connector.operations_per_minute,
            now=now,
        )

        if retry_after is not None:
            return self._result(
                operation,
                ConnectorDecision.RATE_LIMITED,
                "O limite operacional por minuto foi atingido.",
                risk=risk,
                retry_after_seconds=retry_after,
                now=now,
            )

        if risk in _CONFIRMATION_RISKS:
            confirmation = self._check_confirmation(
                operation,
                principal,
                token=confirmation_token,
                risk=risk,
                now=now,
            )

            if confirmation is not None:
                return confirmation

        self._reserve_usage(principal, operation, now)

        if idempotency_identity is not None:
            self._reserved_idempotency_keys.add(idempotency_identity)

        return self._result(
            operation,
            ConnectorDecision.ALLOWED,
            "Operação autorizada pela política do conector.",
            risk=risk,
            now=now,
        )

    def _check_confirmation(
        self,
        operation: ConnectorOperation,
        principal: ConnectorPrincipal,
        *,
        token: str | None,
        risk: ConnectorRisk,
        now: datetime,
    ) -> ConnectorAuthorization | None:
        if token is None:
            new_token = self._new_confirmation_token()
            expires_at = now + self._confirmation_ttl
            self._pending[new_token] = _PendingConfirmation(
                operation_fingerprint=operation.fingerprint(),
                principal_id=principal.principal_id,
                expires_at=expires_at,
            )
            return self._result(
                operation,
                ConnectorDecision.CONFIRMATION_REQUIRED,
                "A operação altera ou acessa estado externo sensível.",
                risk=risk,
                confirmation_token=new_token,
                confirmation_expires_at=expires_at,
                now=now,
            )

        pending = self._pending.get(token)

        if pending is None:
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "Token de confirmação inválido.",
                risk=risk,
                now=now,
            )

        if pending.expires_at <= now:
            self._pending.pop(token, None)
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "Token de confirmação expirado.",
                risk=risk,
                now=now,
            )

        if pending.principal_id != principal.principal_id:
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "A confirmação pertence a outro solicitante.",
                risk=risk,
                now=now,
            )

        if pending.operation_fingerprint != operation.fingerprint():
            return self._result(
                operation,
                ConnectorDecision.DENIED,
                "A operação foi alterada após a solicitação de confirmação.",
                risk=risk,
                now=now,
            )

        self._pending.pop(token, None)
        return None

    def _retry_after(
        self,
        principal: ConnectorPrincipal,
        operation: ConnectorOperation,
        *,
        limit: int,
        now: datetime,
    ) -> float | None:
        key = (principal.principal_id, operation.connector_id)
        history = self._usage.get(key, deque())
        consumed = sum(units for _, units in history)

        if consumed + operation.batch_size <= limit:
            return None

        if not history:
            return 60.0

        release_at = history[0][0] + timedelta(minutes=1)
        return max(0.001, (release_at - now).total_seconds())

    def _reserve_usage(
        self,
        principal: ConnectorPrincipal,
        operation: ConnectorOperation,
        now: datetime,
    ) -> None:
        key = (principal.principal_id, operation.connector_id)
        self._usage.setdefault(key, deque()).append(
            (now, operation.batch_size)
        )

    def _prune_usage(self, now: datetime) -> None:
        threshold = now - timedelta(minutes=1)

        for key, history in tuple(self._usage.items()):
            while history and history[0][0] <= threshold:
                history.popleft()

            if not history:
                self._usage.pop(key, None)

    def _prune_pending(
        self,
        now: datetime,
        *,
        preserve: str | None,
    ) -> None:
        expired = [
            token
            for token, pending in self._pending.items()
            if pending.expires_at <= now and token != preserve
        ]

        for token in expired:
            self._pending.pop(token, None)

    def _new_confirmation_token(self) -> str:
        for _ in range(10):
            token = self._token_factory().strip()

            if token and token not in self._pending:
                return token

        raise RuntimeError("Não foi possível gerar um token de confirmação.")

    def _now(self) -> datetime:
        now = self._clock()

        if now.tzinfo is None:
            raise ValueError("O relógio do conector deve possuir fuso horário.")

        return now.astimezone(timezone.utc)

    @staticmethod
    def _idempotency_identity(
        operation: ConnectorOperation,
    ) -> tuple[str, str] | None:
        if operation.idempotency_key is None:
            return None

        return operation.connector_id, operation.idempotency_key

    @staticmethod
    def _result(
        operation: ConnectorOperation,
        decision: ConnectorDecision,
        reason: str,
        *,
        now: datetime,
        risk: ConnectorRisk | None = None,
        confirmation_token: str | None = None,
        confirmation_expires_at: datetime | None = None,
        retry_after_seconds: float | None = None,
    ) -> ConnectorAuthorization:
        return ConnectorAuthorization(
            operation_id=operation.operation_id,
            decision=decision,
            reason=reason,
            decided_at=now,
            risk=risk,
            confirmation_token=confirmation_token,
            confirmation_expires_at=confirmation_expires_at,
            retry_after_seconds=retry_after_seconds,
        )
