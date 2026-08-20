from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from atlas.connectors import (
    ConnectorCapability,
    ConnectorDecision,
    ConnectorGuard,
    ConnectorManifest,
    ConnectorOperation,
    ConnectorPrincipal,
    ConnectorRegistry,
    ConnectorRisk,
    InMemoryConnectorAuditTrail,
)


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, *, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def make_manifest(
    *,
    enabled: bool = True,
    allow_destructive: bool = False,
    max_batch_size: int = 5,
    operations_per_minute: int = 10,
) -> ConnectorManifest:
    return ConnectorManifest(
        connector_id="business.platform",
        display_name="Plataforma empresarial",
        description="Conector controlado para testes.",
        capabilities=(
            ConnectorCapability(
                name="records.read",
                required_scope="records:read",
                risk=ConnectorRisk.READ_ONLY,
            ),
            ConnectorCapability(
                name="messages.send",
                required_scope="messages:send",
                risk=ConnectorRisk.EXTERNAL_WRITE,
            ),
            ConnectorCapability(
                name="medical.read",
                required_scope="medical:read",
                risk=ConnectorRisk.SENSITIVE,
            ),
            ConnectorCapability(
                name="records.delete",
                required_scope="records:delete",
                risk=ConnectorRisk.DESTRUCTIVE,
            ),
        ),
        max_batch_size=max_batch_size,
        operations_per_minute=operations_per_minute,
        enabled=enabled,
        allow_destructive=allow_destructive,
    )


def make_principal(*scopes: str, principal_id: str = "ssamir") -> ConnectorPrincipal:
    return ConnectorPrincipal(
        principal_id=principal_id,
        role="operator",
        scopes=frozenset(scopes),
    )


def make_guard(
    *,
    manifest: ConnectorManifest | None = None,
    clock: FakeClock | None = None,
    audit: InMemoryConnectorAuditTrail | None = None,
) -> ConnectorGuard:
    return ConnectorGuard(
        ConnectorRegistry((manifest or make_manifest(),)),
        audit=audit,
        confirmation_ttl_seconds=30,
        clock=clock,
        token_factory=lambda: "confirmation-token",
    )


def test_read_only_operation_is_allowed_with_required_scope() -> None:
    guard = make_guard()
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="records.read",
    )

    result = guard.authorize(operation, make_principal("records:read"))

    assert result.decision is ConnectorDecision.ALLOWED
    assert result.allowed is True
    assert result.risk is ConnectorRisk.READ_ONLY


def test_missing_scope_and_disabled_connector_fail_closed() -> None:
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="records.read",
    )

    missing_scope = make_guard().authorize(operation, make_principal())
    disabled = make_guard(
        manifest=make_manifest(enabled=False)
    ).authorize(operation, make_principal("records:read"))

    assert missing_scope.decision is ConnectorDecision.DENIED
    assert "Escopo" in missing_scope.reason
    assert disabled.decision is ConnectorDecision.DENIED
    assert "desativado" in disabled.reason


def test_unknown_connector_or_capability_is_denied() -> None:
    guard = make_guard()
    principal = make_principal("records:read")

    unknown_connector = guard.authorize(
        ConnectorOperation(
            connector_id="unknown.platform",
            capability="records.read",
        ),
        principal,
    )
    unknown_capability = guard.authorize(
        ConnectorOperation(
            connector_id="business.platform",
            capability="records.unknown",
        ),
        principal,
    )

    assert unknown_connector.decision is ConnectorDecision.DENIED
    assert unknown_capability.decision is ConnectorDecision.DENIED


def test_external_write_requires_idempotency_and_confirmation() -> None:
    guard = make_guard()
    principal = make_principal("messages:send")
    missing_key = ConnectorOperation(
        connector_id="business.platform",
        capability="messages.send",
        parameters={"recipient_count": 1},
    )
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="messages.send",
        parameters={"recipient_count": 1},
        idempotency_key="campaign-1-recipient-1",
    )

    denied = guard.authorize(missing_key, principal)
    pending = guard.authorize(operation, principal)
    allowed = guard.authorize(
        operation,
        principal,
        confirmation_token=pending.confirmation_token,
    )
    duplicate = guard.authorize(operation, principal)

    assert denied.decision is ConnectorDecision.DENIED
    assert "idempotência" in denied.reason
    assert pending.requires_confirmation is True
    assert pending.confirmation_token == "confirmation-token"
    assert allowed.decision is ConnectorDecision.ALLOWED
    assert duplicate.decision is ConnectorDecision.DUPLICATE


def test_confirmation_is_bound_to_operation_and_principal() -> None:
    guard = make_guard()
    owner = make_principal("messages:send")
    other = make_principal("messages:send", principal_id="other")
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="messages.send",
        parameters={"message": "Olá"},
        idempotency_key="message-1",
        operation_id="fixed-operation",
    )
    pending = guard.authorize(operation, owner)
    altered = ConnectorOperation(
        connector_id="business.platform",
        capability="messages.send",
        parameters={"message": "Conteúdo alterado"},
        idempotency_key="message-1",
        operation_id="fixed-operation",
    )

    wrong_principal = guard.authorize(
        operation,
        other,
        confirmation_token=pending.confirmation_token,
    )
    altered_result = guard.authorize(
        altered,
        owner,
        confirmation_token=pending.confirmation_token,
    )
    original_result = guard.authorize(
        operation,
        owner,
        confirmation_token=pending.confirmation_token,
    )

    assert wrong_principal.decision is ConnectorDecision.DENIED
    assert "outro solicitante" in wrong_principal.reason
    assert altered_result.decision is ConnectorDecision.DENIED
    assert "alterada" in altered_result.reason
    assert original_result.decision is ConnectorDecision.ALLOWED


def test_confirmation_expires_and_can_be_revoked() -> None:
    clock = FakeClock()
    guard = make_guard(clock=clock)
    principal = make_principal("medical:read")
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="medical.read",
    )
    first = guard.authorize(operation, principal)
    assert guard.revoke_confirmation(first.confirmation_token or "") is True
    revoked = guard.authorize(
        operation,
        principal,
        confirmation_token=first.confirmation_token,
    )
    second = guard.authorize(operation, principal)
    clock.advance(seconds=31)
    expired = guard.authorize(
        operation,
        principal,
        confirmation_token=second.confirmation_token,
    )

    assert revoked.decision is ConnectorDecision.DENIED
    assert expired.decision is ConnectorDecision.DENIED
    assert "expirado" in expired.reason


def test_batch_limit_and_rolling_rate_limit_count_each_item() -> None:
    clock = FakeClock()
    guard = make_guard(
        manifest=make_manifest(
            max_batch_size=3,
            operations_per_minute=3,
        ),
        clock=clock,
    )
    principal = make_principal("records:read")

    oversized = guard.authorize(
        ConnectorOperation(
            connector_id="business.platform",
            capability="records.read",
            batch_size=4,
        ),
        principal,
    )
    first = guard.authorize(
        ConnectorOperation(
            connector_id="business.platform",
            capability="records.read",
            batch_size=2,
        ),
        principal,
    )
    limited = guard.authorize(
        ConnectorOperation(
            connector_id="business.platform",
            capability="records.read",
            batch_size=2,
        ),
        principal,
    )
    clock.advance(seconds=61)
    released = guard.authorize(
        ConnectorOperation(
            connector_id="business.platform",
            capability="records.read",
            batch_size=2,
        ),
        principal,
    )

    assert oversized.decision is ConnectorDecision.DENIED
    assert first.decision is ConnectorDecision.ALLOWED
    assert limited.decision is ConnectorDecision.RATE_LIMITED
    assert limited.retry_after_seconds == 60.0
    assert released.decision is ConnectorDecision.ALLOWED


def test_destructive_operation_is_blocked_unless_manifest_opts_in() -> None:
    principal = make_principal("records:delete")
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="records.delete",
        idempotency_key="delete-record-1",
    )

    blocked = make_guard().authorize(operation, principal)
    enabled_guard = make_guard(
        manifest=make_manifest(allow_destructive=True)
    )
    pending = enabled_guard.authorize(operation, principal)

    assert blocked.decision is ConnectorDecision.DENIED
    assert "destrutivas" in blocked.reason
    assert pending.decision is ConnectorDecision.CONFIRMATION_REQUIRED


def test_wildcard_scope_allows_capability() -> None:
    result = make_guard().authorize(
        ConnectorOperation(
            connector_id="business.platform",
            capability="records.read",
        ),
        make_principal("*"),
    )

    assert result.decision is ConnectorDecision.ALLOWED


def test_audit_never_stores_parameters_or_raw_idempotency_key() -> None:
    audit = InMemoryConnectorAuditTrail()
    guard = make_guard(audit=audit)
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="messages.send",
        parameters={"phone": "+5592999999999", "message": "segredo"},
        idempotency_key="private-idempotency-key",
    )

    guard.authorize(operation, make_principal("messages:send"))
    records = audit.list_records(limit=10)
    record = records[0]

    assert len(records) == 1
    assert record.decision is ConnectorDecision.CONFIRMATION_REQUIRED
    assert record.idempotency_fingerprint is not None
    assert record.idempotency_fingerprint != "private-idempotency-key"
    assert not hasattr(record, "parameters")
    assert "+5592999999999" not in repr(record)
    assert "segredo" not in repr(record)


def test_confirmation_and_idempotency_are_thread_safe() -> None:
    guard = make_guard()
    principal = make_principal("messages:send")
    operation = ConnectorOperation(
        connector_id="business.platform",
        capability="messages.send",
        idempotency_key="thread-safe-operation",
    )
    pending = guard.authorize(operation, principal)

    def authorize() -> ConnectorDecision:
        return guard.authorize(
            operation,
            principal,
            confirmation_token=pending.confirmation_token,
        ).decision

    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(lambda _: authorize(), range(2)))

    assert sorted(decisions) == sorted(
        [ConnectorDecision.ALLOWED, ConnectorDecision.DUPLICATE]
    )
