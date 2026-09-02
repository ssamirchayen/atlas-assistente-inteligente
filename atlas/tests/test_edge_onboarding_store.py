from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from atlas.edge import (
    EmployeeOnboarding,
    EmployeeOnboardingReport,
    EmployeeOnboardingStatus,
    EmployeeOnboardingStore,
    EmployeeOnboardingStoreError,
)


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _record(
    suffix="a",
    *,
    status=EmployeeOnboardingStatus.AWAITING_APPROVAL,
    revision=1,
):
    return EmployeeOnboarding(
        onboarding_id="edgeonb_" + suffix * 32,
        organization_id="empresa-manaus",
        device_id="edge_" + "d" * 32,
        employee_reference_hash=sha256(f"employee-{suffix}".encode()).hexdigest(),
        requester_hash=sha256(f"requester-{suffix}".encode()).hexdigest(),
        profile_id="employee-sales",
        status=status,
        created_at=NOW,
        updated_at=NOW,
        plan_request_id="edgeplan_" + suffix * 32,
        plan_digest=sha256(f"plan-{suffix}".encode()).hexdigest(),
        revision=revision,
    )


def test_onboarding_round_trip_preserves_only_safe_contract() -> None:
    original = _record()

    restored = EmployeeOnboarding.from_dict(original.as_dict())

    assert restored == original
    assert restored.terminal is False


def test_terminal_statuses_are_exposed_consistently() -> None:
    for status in (
        EmployeeOnboardingStatus.SIMULATED,
        EmployeeOnboardingStatus.SUCCEEDED,
        EmployeeOnboardingStatus.FAILED,
        EmployeeOnboardingStatus.CANCELLED,
    ):
        assert replace(_record(), status=status).terminal is True


def test_invalid_onboarding_identifier_is_rejected() -> None:
    with pytest.raises(ValueError, match="identificador"):
        replace(_record(), onboarding_id="onboarding-user-controlled")


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="fuso"):
        replace(_record(), updated_at=datetime(2026, 9, 1))


def test_report_rejects_negative_counters() -> None:
    with pytest.raises(ValueError, match="não podem ser negativos"):
        EmployeeOnboardingReport(
            organization_id="empresa-manaus",
            total=1,
            active=-1,
            action_required=0,
            simulated=0,
            succeeded=0,
            failed=0,
            cancelled=0,
            generated_at=NOW,
        )


def test_report_requires_counters_to_match_total() -> None:
    with pytest.raises(ValueError, match="não fecham"):
        EmployeeOnboardingReport(
            organization_id="empresa-manaus",
            total=2,
            active=1,
            action_required=0,
            simulated=0,
            succeeded=0,
            failed=0,
            cancelled=0,
            generated_at=NOW,
        )


def test_store_persists_and_reloads_records(tmp_path) -> None:
    path = tmp_path / "onboardings.json"
    store = EmployeeOnboardingStore(path)
    store.save(_record())

    reloaded = EmployeeOnboardingStore(path)

    assert reloaded.list() == (_record(),)
    assert reloaded.get(_record().onboarding_id) == _record()


def test_store_never_persists_tokens_or_private_references(tmp_path) -> None:
    path = tmp_path / "onboardings.json"
    store = EmployeeOnboardingStore(path)
    store.save(_record())
    payload = path.read_text(encoding="utf-8")

    assert "token" not in payload.casefold()
    assert "authorization_id" not in payload
    assert "maria@empresa.test" not in payload


def test_corrupted_store_fails_closed(tmp_path) -> None:
    path = tmp_path / "onboardings.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(EmployeeOnboardingStoreError, match="corrompido"):
        EmployeeOnboardingStore(path)


def test_duplicate_persisted_ids_fail_closed(tmp_path) -> None:
    path = tmp_path / "onboardings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "records": [_record().as_dict(), _record().as_dict()],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(EmployeeOnboardingStoreError, match="duplicados"):
        EmployeeOnboardingStore(path)


def test_stale_revision_cannot_overwrite_newer_state(tmp_path) -> None:
    store = EmployeeOnboardingStore(tmp_path / "onboardings.json")
    original = _record()
    store.save(original)

    with pytest.raises(ValueError, match="revisão"):
        store.save(replace(original, status=EmployeeOnboardingStatus.AUTHORIZED))


def test_terminal_record_is_pruned_when_history_reaches_limit(tmp_path) -> None:
    store = EmployeeOnboardingStore(
        tmp_path / "onboardings.json",
        max_records=1,
    )
    store.save(_record("a", status=EmployeeOnboardingStatus.CANCELLED))
    second = _record("b")

    store.save(second)

    assert store.list() == (second,)


def test_active_history_limit_fails_without_losing_existing_record(tmp_path) -> None:
    store = EmployeeOnboardingStore(
        tmp_path / "onboardings.json",
        max_records=1,
    )
    first = _record("a")
    store.save(first)

    with pytest.raises(OverflowError, match="atingiu o limite"):
        store.save(_record("b"))

    assert store.list() == (first,)


def test_oversized_write_rolls_back_in_memory_state(tmp_path) -> None:
    store = EmployeeOnboardingStore(
        tmp_path / "onboardings.json",
        max_bytes=32,
    )

    with pytest.raises(EmployeeOnboardingStoreError, match="excede"):
        store.save(_record())

    assert store.list() == ()


def test_updated_record_requires_a_newer_revision(tmp_path) -> None:
    store = EmployeeOnboardingStore(tmp_path / "onboardings.json")
    original = _record()
    store.save(original)
    updated = replace(
        original,
        status=EmployeeOnboardingStatus.AUTHORIZED,
        updated_at=NOW + timedelta(seconds=1),
        revision=2,
    )

    store.save(updated)

    assert store.get(original.onboarding_id) == updated
