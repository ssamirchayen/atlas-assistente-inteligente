from __future__ import annotations

from threading import Thread

import pytest

from atlas.privacy.minimization import Pseudonymizer
from atlas.privacy.models import DataCategory
from atlas.privacy.policy import DeclaredLegalBasis
from atlas.privacy.subject_data import InMemorySubjectDataSource


SECRET = b"atlas-test-rights-secret-key-at-least-32-bytes"


def subject(value: str = "subject-123") -> str:
    return Pseudonymizer(SECRET).pseudonymize(
        value,
        namespace="rights:tenant-a:subject",
    )


def source(*, retention_reasons: tuple[str, ...] = ()) -> InMemorySubjectDataSource:
    return InMemorySubjectDataSource(
        source_id="session-store",
        organization_id="tenant-a",
        record_id="session.operational_history",
        categories=(DataCategory.IDENTIFICATION,),
        fields=("display_name", "email", "preference"),
        legal_basis=DeclaredLegalBasis.LEGAL_OBLIGATION,
        retention_reasons=retention_reasons,
    )


def test_source_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        InMemorySubjectDataSource(
            source_id="invalid source",
            organization_id="tenant-a",
            record_id="session.operational_history",
            categories=(DataCategory.IDENTIFICATION,),
            fields=("name",),
            legal_basis=DeclaredLegalBasis.LEGAL_OBLIGATION,
        )
    with pytest.raises(TypeError):
        InMemorySubjectDataSource(
            source_id="valid-source",
            organization_id="tenant-a",
            record_id="session.operational_history",
            categories=("identification",),  # type: ignore[arg-type]
            fields=("name",),
            legal_basis=DeclaredLegalBasis.LEGAL_OBLIGATION,
        )


def test_put_rejects_raw_subject_and_unknown_fields() -> None:
    target = source()
    with pytest.raises(ValueError, match="subject_pseudonym"):
        target.put("subject-123", {"display_name": "Ada"})
    with pytest.raises(ValueError, match="não declarados"):
        target.put(subject(), {"cpf": "not-allowed"})


def test_read_returns_only_selected_fields_and_is_immutable() -> None:
    target = source()
    target.put(
        subject(),
        {
            "display_name": "Ada",
            "email": "ada@example.test",
            "preference": "dark",
        },
    )
    result = target.read(subject(), ("display_name", "preference"))
    assert dict(result) == {"display_name": "Ada", "preference": "dark"}
    with pytest.raises(TypeError):
        result["display_name"] = "changed"  # type: ignore[index]


def test_read_rejects_undeclared_fields() -> None:
    with pytest.raises(ValueError, match="não declarados"):
        source().read(subject(), ("cpf",))


def test_correction_changes_only_declared_fields() -> None:
    target = source()
    target.put(subject(), {"display_name": "Ada", "email": "old@example.test"})
    changed = target.correct(subject(), {"email": "new@example.test"})
    assert changed == 1
    assert target.read(subject(), ("email",))["email"] == "new@example.test"
    with pytest.raises(ValueError):
        target.correct(subject(), {"cpf": "not-allowed"})


def test_correction_and_deletion_of_absent_subject_are_idempotent() -> None:
    target = source()
    assert target.correct(subject(), {"email": "new@example.test"}) == 0
    assert target.delete(subject()) == 0


def test_deletion_plan_exposes_only_counts_and_reason_codes() -> None:
    target = source(retention_reasons=("legal_obligation",))
    target.put(subject(), {"display_name": "Ada"})
    plan = target.plan_delete(subject())
    assert plan.record_count == 1
    assert plan.can_delete is False
    assert plan.retention_reasons == ("legal_obligation",)
    assert "Ada" not in repr(plan)
    with pytest.raises(PermissionError, match="retenção"):
        target.delete(subject())


def test_delete_removes_subject_without_retention_restriction() -> None:
    target = source()
    target.put(subject(), {"display_name": "Ada"})
    assert target.delete(subject()) == 1
    assert target.has_subject(subject()) is False


def test_concurrent_subject_inserts_remain_isolated() -> None:
    target = source()

    def worker(index: int) -> None:
        target.put(subject(f"subject-{index}"), {"display_name": f"User {index}"})

    threads = [Thread(target=worker, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(target.has_subject(subject(f"subject-{index}")) for index in range(20))
