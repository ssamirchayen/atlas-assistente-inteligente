from __future__ import annotations

from dataclasses import replace

import pytest

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
    RiskLevel,
    StorageKind,
)


def _record(**changes: object) -> ProcessingRecord:
    values = {
        "record_id": "test.personal_data",
        "name": "Tratamento de teste",
        "component": "atlas.test",
        "nature": DataNature.PERSONAL,
        "categories": (DataCategory.IDENTIFICATION,),
        "subjects": (DataSubject.USER,),
        "operations": (ProcessingOperation.COLLECT, ProcessingOperation.STORE),
        "purpose": "Validar o modelo.",
        "source": "Teste automatizado.",
        "recipients": ("Atlas local",),
        "stores": (
            DataStore(
                location="data/test.db",
                kind=StorageKind.SQLITE,
                provider="Atlas local",
                local=True,
                encrypted_at_rest=False,
            ),
        ),
        "retention": RetentionPolicy(
            mode=RetentionMode.UNDEFINED,
            description="Ainda não definida.",
        ),
        "controller_role": "Organização de teste",
        "operator_roles": ("Operador",),
        "legal_basis_status": (
            LegalBasisStatus.REQUIRES_CONTROLLER_DEFINITION
        ),
        "implemented_controls": ("local_storage",),
        "required_controls": ("local_storage", "retention_schedule"),
    }
    values.update(changes)
    return ProcessingRecord(**values)


def test_data_store_rejects_empty_location() -> None:
    with pytest.raises(ValueError, match="localização"):
        DataStore(
            location=" ",
            kind=StorageKind.SQLITE,
            provider="Atlas",
            local=True,
            encrypted_at_rest=False,
        )


def test_data_store_rejects_ephemeral_sqlite() -> None:
    with pytest.raises(ValueError, match="transitório"):
        DataStore(
            location="data/test.db",
            kind=StorageKind.SQLITE,
            provider="Atlas",
            local=True,
            encrypted_at_rest=False,
            ephemeral=True,
        )


def test_configured_retention_requires_valid_env_key() -> None:
    with pytest.raises(ValueError, match="indicar sua chave"):
        RetentionPolicy(
            mode=RetentionMode.CONFIGURED,
            description="Prazo configurável.",
        )
    with pytest.raises(ValueError, match="chave de retenção"):
        RetentionPolicy(
            mode=RetentionMode.CONFIGURED,
            description="Prazo configurável.",
            configuration_key="INVALID",
        )


def test_processing_record_rejects_unsafe_id() -> None:
    with pytest.raises(ValueError, match="record_id"):
        _record(record_id="Dados do usuário")


def test_personal_record_requires_subject() -> None:
    with pytest.raises(ValueError, match="titulares"):
        _record(subjects=())


def test_personal_record_cannot_skip_legal_basis_review() -> None:
    with pytest.raises(ValueError, match="base legal"):
        _record(legal_basis_status=LegalBasisStatus.NOT_APPLICABLE)


def test_confirmed_legal_basis_requires_reference() -> None:
    with pytest.raises(ValueError, match="referência"):
        _record(legal_basis_status=LegalBasisStatus.CONFIRMED_BY_CONTROLLER)


def test_confirmed_legal_basis_accepts_controller_reference() -> None:
    record = _record(
        legal_basis_status=LegalBasisStatus.CONFIRMED_BY_CONTROLLER,
        legal_basis_reference="Registro interno ROPA-2026-001",
    )
    assert record.legal_basis_reference == "Registro interno ROPA-2026-001"


def test_record_rejects_duplicate_categories() -> None:
    with pytest.raises(ValueError, match="duplicidades"):
        _record(
            categories=(
                DataCategory.IDENTIFICATION,
                DataCategory.IDENTIFICATION,
            )
        )


def test_record_rejects_invalid_control_identifier() -> None:
    with pytest.raises(ValueError, match="controle inválido"):
        _record(required_controls=("Controle com espaço",))


def test_unresolved_controls_keep_declared_order() -> None:
    record = _record(
        implemented_controls=("local_storage",),
        required_controls=(
            "retention_schedule",
            "local_storage",
            "at_rest_encryption",
        ),
    )
    assert record.unresolved_controls == (
        "retention_schedule",
        "at_rest_encryption",
    )


def test_sensitive_child_record_is_critical() -> None:
    record = replace(
        _record(),
        nature=DataNature.SENSITIVE_PERSONAL,
        subjects=(DataSubject.CHILD_OR_ADOLESCENT,),
        categories=(DataCategory.HEALTH,),
    )
    assert record.risk_level is RiskLevel.CRITICAL


def test_international_personal_record_is_high_risk() -> None:
    record = replace(_record(), international_transfer=True)
    assert record.risk_level is RiskLevel.HIGH


def test_non_personal_record_is_low_risk() -> None:
    record = _record(
        nature=DataNature.NON_PERSONAL,
        subjects=(),
        legal_basis_status=LegalBasisStatus.NOT_APPLICABLE,
    )
    assert record.risk_level is RiskLevel.LOW


def test_record_serialization_contains_metadata_only() -> None:
    payload = _record().as_dict()
    assert payload["record_id"] == "test.personal_data"
    assert payload["nature"] == "personal"
    assert payload["unresolved_controls"] == ["retention_schedule"]
    assert payload["stores"][0]["location"] == "data/test.db"

