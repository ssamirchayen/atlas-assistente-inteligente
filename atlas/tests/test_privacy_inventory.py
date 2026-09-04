from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json

import pytest

from atlas.privacy.inventory import IssueSeverity, ProcessingInventory
from atlas.privacy.models import (
    DataCategory,
    DataNature,
    DataStore,
    DataSubject,
    LegalBasisStatus,
    ProcessingOperation,
    ProcessingRecord,
    RetentionMode,
    RetentionPolicy,
    StorageKind,
)


def _record(record_id: str = "test.record") -> ProcessingRecord:
    return ProcessingRecord(
        record_id=record_id,
        name="Registro",
        component="atlas.test.component",
        nature=DataNature.PERSONAL,
        categories=(DataCategory.IDENTIFICATION,),
        subjects=(DataSubject.USER,),
        operations=(ProcessingOperation.COLLECT, ProcessingOperation.STORE),
        purpose="Teste do inventário.",
        source="Teste automatizado.",
        recipients=("Atlas local",),
        stores=(
            DataStore(
                location="data/test.json",
                kind=StorageKind.JSON,
                provider="Atlas",
                local=True,
                encrypted_at_rest=False,
            ),
        ),
        retention=RetentionPolicy(
            RetentionMode.UNDEFINED,
            "Prazo ainda não definido.",
        ),
        controller_role="Organização",
        operator_roles=("Operador",),
        legal_basis_status=LegalBasisStatus.REQUIRES_CONTROLLER_DEFINITION,
        implemented_controls=("local_storage",),
        required_controls=("local_storage", "retention_schedule"),
    )


def test_inventory_rejects_empty_collection() -> None:
    with pytest.raises(ValueError, match="não pode ser vazio"):
        ProcessingInventory(())


def test_inventory_rejects_duplicate_record_ids() -> None:
    record = _record()
    with pytest.raises(ValueError, match="duplicado"):
        ProcessingInventory((record, record))


def test_inventory_sorts_records_by_id() -> None:
    inventory = ProcessingInventory((_record("z.last"), _record("a.first")))
    assert [record.record_id for record in inventory.records] == [
        "a.first",
        "z.last",
    ]


def test_inventory_get_rejects_unknown_record() -> None:
    inventory = ProcessingInventory((_record(),))
    with pytest.raises(KeyError, match="não inventariado"):
        inventory.get("missing.record")


def test_find_by_component_is_case_insensitive() -> None:
    inventory = ProcessingInventory((_record(),))
    assert inventory.find_by_component("ATLAS.TEST") == (_record(),)
    with pytest.raises(ValueError, match="não pode ser vazio"):
        inventory.find_by_component("  ")


def test_analysis_marks_pending_basis_retention_and_control() -> None:
    fixed = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    report = ProcessingInventory(
        (_record(),), clock=lambda: fixed
    ).analyze()
    codes = {issue.code for issue in report.issues}
    assert codes == {
        "legal_basis_pending",
        "retention_undefined",
        "control_missing.retention_schedule",
    }
    assert report.generated_at == fixed
    assert report.requires_action is True
    assert report.high_or_critical_issues == 3


def test_analysis_marks_external_policy_and_transfer() -> None:
    record = replace(
        _record(),
        retention=RetentionPolicy(
            RetentionMode.EXTERNAL_POLICY,
            "Política do provedor.",
        ),
        international_transfer=True,
        required_controls=(),
    )
    report = ProcessingInventory((record,)).analyze()
    issues = {issue.code: issue for issue in report.issues}
    assert issues["external_retention_requires_evidence"].severity is (
        IssueSeverity.WARNING
    )
    assert issues["international_transfer_review"].severity is IssueSeverity.HIGH


def test_analysis_marks_children_and_automated_decision() -> None:
    record = replace(
        _record(),
        nature=DataNature.SENSITIVE_PERSONAL,
        categories=(DataCategory.HEALTH,),
        subjects=(DataSubject.CHILD_OR_ADOLESCENT,),
        automated_decision=True,
        required_controls=("child_safeguards",),
    )
    report = ProcessingInventory((record,)).analyze()
    issues = {issue.code: issue for issue in report.issues}
    assert issues["child_data_specific_review"].severity is IssueSeverity.CRITICAL
    assert issues["automated_decision_review"].severity is IssueSeverity.HIGH
    assert issues["control_missing.child_safeguards"].severity is (
        IssueSeverity.CRITICAL
    )


def test_analysis_counts_nature_and_risk() -> None:
    non_personal = replace(
        _record("test.non_personal"),
        nature=DataNature.NON_PERSONAL,
        subjects=(),
        legal_basis_status=LegalBasisStatus.NOT_APPLICABLE,
    )
    report = ProcessingInventory((_record(), non_personal)).analyze()
    assert report.counts_by_nature["personal"] == 1
    assert report.counts_by_nature["non_personal"] == 1
    assert report.counts_by_risk["moderate"] == 1
    assert report.counts_by_risk["low"] == 1


def test_inventory_rejects_naive_clock() -> None:
    inventory = ProcessingInventory(
        (_record(),), clock=lambda: datetime(2026, 9, 1)
    )
    with pytest.raises(ValueError, match="fuso horário"):
        inventory.analyze()


def test_export_json_writes_atomic_structured_inventory(tmp_path) -> None:
    fixed = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    inventory = ProcessingInventory((_record(),), clock=lambda: fixed)
    target = inventory.export_json(tmp_path / "reports" / "inventory.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["report"]["total_records"] == 1
    assert payload["records"][0]["record_id"] == "test.record"
    assert not target.with_suffix(".json.tmp").exists()

