from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Thread

import pytest

from atlas.privacy.consent import ConsentRegistry, ConsentStatus
from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory


SECRET = b"atlas-test-privacy-secret-key-32-bytes-minimum"


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current


def registry(clock: MutableClock) -> ConsentRegistry:
    return ConsentRegistry(Pseudonymizer(SECRET), clock=clock)


def grant(
    target: ConsentRegistry,
    *,
    organization_id: str = "tenant-a",
    subject_id: str = "subject-123",
    expires_at: datetime | None = None,
):
    return target.grant(
        organization_id=organization_id,
        subject_id=subject_id,
        record_id="memory.long_term_and_embeddings",
        purpose="remember.preference",
        categories=(DataCategory.CONVERSATION, DataCategory.PREFERENCES),
        evidence="Checkbox version 2 accepted at 2026-01-02T12:00Z",
        granted_by="operator-1",
        expires_at=expires_at,
    )


def find(target: ConsentRegistry, **overrides: object):
    values: dict[str, object] = {
        "organization_id": "tenant-a",
        "subject_id": "subject-123",
        "record_id": "memory.long_term_and_embeddings",
        "purpose": "remember.preference",
        "categories": (DataCategory.CONVERSATION,),
    }
    values.update(overrides)
    return target.find_valid(**values)


def test_grant_stores_only_pseudonymous_subject_and_evidence_digest() -> None:
    clock = MutableClock()
    receipt = grant(registry(clock))
    assert receipt.status_at(clock()) is ConsentStatus.ACTIVE
    assert receipt.subject_pseudonym.startswith("psn_")
    assert "subject-123" not in repr(receipt)
    assert len(receipt.evidence_digest) == 64
    assert "Checkbox" not in repr(receipt)


def test_find_valid_enforces_scope_and_receipt_id() -> None:
    clock = MutableClock()
    target = registry(clock)
    receipt = grant(target)
    assert find(target, receipt_id=receipt.receipt_id) == receipt
    assert find(target, categories=(DataCategory.HEALTH,)) is None
    assert find(target, receipt_id="0" * 32) is None


def test_consent_is_isolated_by_organization_and_subject() -> None:
    clock = MutableClock()
    target = registry(clock)
    grant(target)
    assert find(target, organization_id="tenant-b") is None
    assert find(target, subject_id="subject-999") is None


def test_expired_consent_is_not_valid() -> None:
    clock = MutableClock()
    target = registry(clock)
    receipt = grant(target, expires_at=clock() + timedelta(hours=1))
    clock.current += timedelta(hours=1)
    assert receipt.status_at(clock()) is ConsentStatus.EXPIRED
    assert find(target) is None


def test_naive_expiry_is_rejected() -> None:
    clock = MutableClock()
    with pytest.raises(ValueError, match="fuso horário"):
        grant(target=registry(clock), expires_at=datetime(2026, 1, 3))


def test_revoke_is_idempotent_and_invalidates_consent() -> None:
    clock = MutableClock()
    target = registry(clock)
    receipt = grant(target)
    revoked = target.revoke(
        receipt.receipt_id,
        organization_id="tenant-a",
        revoked_by="privacy-admin",
    )
    repeated = target.revoke(
        receipt.receipt_id,
        organization_id="tenant-a",
        revoked_by="other-admin",
    )
    assert revoked == repeated
    assert revoked.status_at(clock()) is ConsentStatus.REVOKED
    assert find(target) is None


def test_revoke_rejects_cross_tenant_access_and_unknown_receipt() -> None:
    clock = MutableClock()
    target = registry(clock)
    receipt = grant(target)
    with pytest.raises(PermissionError):
        target.revoke(
            receipt.receipt_id,
            organization_id="tenant-b",
            revoked_by="operator-2",
        )
    with pytest.raises(KeyError):
        target.revoke(
            "f" * 32,
            organization_id="tenant-a",
            revoked_by="operator-1",
        )


def test_revoked_latest_receipt_does_not_revive_older_grant() -> None:
    clock = MutableClock()
    target = registry(clock)
    older = grant(target)
    clock.current += timedelta(seconds=1)
    latest = grant(target)
    target.revoke(
        latest.receipt_id,
        organization_id="tenant-a",
        revoked_by="operator-1",
    )
    assert older.status_at(clock()) is ConsentStatus.ACTIVE
    assert find(target) is None


def test_latest_receipt_wins_even_when_clock_has_same_timestamp() -> None:
    clock = MutableClock()
    target = registry(clock)
    older = grant(target)
    latest = grant(target)
    target.revoke(
        latest.receipt_id,
        organization_id="tenant-a",
        revoked_by="operator-1",
    )
    assert older.status_at(clock()) is ConsentStatus.ACTIVE
    assert find(target) is None


def test_list_for_subject_does_not_leak_other_subject_or_tenant() -> None:
    clock = MutableClock()
    target = registry(clock)
    own = grant(target)
    grant(target, subject_id="subject-999")
    grant(target, organization_id="tenant-b")
    assert target.list_for_subject(
        organization_id="tenant-a",
        subject_id="subject-123",
    ) == (own,)


def test_concurrent_grants_have_unique_receipts() -> None:
    clock = MutableClock()
    target = registry(clock)
    receipts: list[str] = []

    def worker() -> None:
        receipts.append(grant(target).receipt_id)

    threads = [Thread(target=worker) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(receipts) == 12
    assert len(set(receipts)) == 12
