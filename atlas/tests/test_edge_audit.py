from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from atlas.edge import (
    EdgeAction,
    EdgeAuditOutcome,
    EdgePrincipal,
    EdgeRole,
    InMemoryEdgeAuditTrail,
    SqliteEdgeAuditTrail,
    build_edge_audit_event,
)


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)
DEVICE_ID = "edge_" + "a" * 32


def _event(principal, *, occurred_at=NOW, reason="policy_authorized"):
    return build_edge_audit_event(
        principal,
        device_id=DEVICE_ID,
        action=EdgeAction.PLAN_PREPARE,
        outcome=EdgeAuditOutcome.AUTHORIZED,
        reason_code=reason,
        occurred_at=occurred_at,
        target_id="employee-secure",
        dry_run=True,
    )


def test_sqlite_audit_persists_only_hashed_actor(tmp_path) -> None:
    principal = EdgePrincipal(
        "pessoa.sensivel@empresa.test",
        "empresa-manaus",
        EdgeRole.OPERATOR,
    )
    path = tmp_path / "audit.db"
    audit = SqliteEdgeAuditTrail(path, clock=lambda: NOW)
    audit.record(_event(principal))

    stored = audit.query("empresa-manaus")
    raw = path.read_bytes()

    assert stored[0].actor_hash == principal.principal_hash
    assert b"pessoa.sensivel" not in raw


def test_query_is_isolated_by_organization(tmp_path) -> None:
    audit = SqliteEdgeAuditTrail(tmp_path / "audit.db", clock=lambda: NOW)
    first = EdgePrincipal("auditor.um", "empresa-manaus", EdgeRole.AUDITOR)
    second = EdgePrincipal("auditor.dois", "empresa-belem", EdgeRole.AUDITOR)
    audit.record(_event(first))
    audit.record(_event(second))

    assert len(audit.query("empresa-manaus")) == 1
    assert audit.query("empresa-manaus")[0].organization_id == "empresa-manaus"


def test_retention_removes_expired_events(tmp_path) -> None:
    audit = SqliteEdgeAuditTrail(
        tmp_path / "audit.db",
        retention_days=7,
        clock=lambda: NOW,
    )
    principal = EdgePrincipal("auditor.um", "empresa-manaus", EdgeRole.AUDITOR)
    audit.record(_event(principal, occurred_at=NOW - timedelta(days=8)))
    audit.record(_event(principal, occurred_at=NOW))

    assert len(audit.query("empresa-manaus")) == 1


def test_max_event_limit_prunes_oldest_rows(tmp_path) -> None:
    audit = SqliteEdgeAuditTrail(
        tmp_path / "audit.db",
        max_events=2,
        clock=lambda: NOW,
    )
    principal = EdgePrincipal("auditor.um", "empresa-manaus", EdgeRole.AUDITOR)
    for offset in range(3):
        audit.record(
            _event(
                principal,
                occurred_at=NOW + timedelta(seconds=offset),
                reason=f"event_{offset}",
            )
        )

    assert [event.reason_code for event in audit.query("empresa-manaus")] == [
        "event_2",
        "event_1",
    ]


def test_in_memory_audit_enforces_query_limit() -> None:
    audit = InMemoryEdgeAuditTrail()

    with pytest.raises(ValueError, match="entre 1 e 500"):
        audit.query("empresa-manaus", limit=0)


def test_database_has_no_free_form_metadata_column(tmp_path) -> None:
    path = tmp_path / "audit.db"
    SqliteEdgeAuditTrail(path, clock=lambda: NOW)

    with sqlite3.connect(path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(edge_audit)")
        }

    assert "metadata" not in columns
    assert "token" not in columns
    assert "employee_reference" not in columns
