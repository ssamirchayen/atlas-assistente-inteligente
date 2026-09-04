from __future__ import annotations

from pathlib import Path

from atlas.privacy.catalog import build_default_privacy_inventory
from atlas.privacy.models import (
    DataNature,
    DataSubject,
    LegalBasisStatus,
    RetentionMode,
    RiskLevel,
)


EXPECTED_RECORD_IDS = {
    "api.security_audit",
    "audit.connector_and_vision_metadata",
    "core.conversation_context",
    "edge.device_and_employee_onboarding",
    "internet.search_queries",
    "logs.application_diagnostics",
    "memory.long_term_and_embeddings",
    "privacy.policy_decision_audit",
    "privacy.impact_assessments",
    "privacy.incident_response_records",
    "privacy.retention_disposal_actions",
    "privacy.subject_rights_requests",
    "scheduler.jobs",
    "school.crm_leads",
    "secrets.runtime_credentials",
    "session.operational_history",
    "vision.screen_capture",
    "voice.neural_tts_and_cache",
    "voice.speech_recognition",
}


def test_default_catalog_covers_current_atlas_data_flows() -> None:
    inventory = build_default_privacy_inventory()
    assert {record.record_id for record in inventory.records} == EXPECTED_RECORD_IDS


def test_catalog_keeps_legal_decisions_pending_for_controller() -> None:
    inventory = build_default_privacy_inventory()
    assert all(
        record.legal_basis_status
        is LegalBasisStatus.REQUIRES_CONTROLLER_DEFINITION
        for record in inventory.records
    )
    assert all(record.legal_basis_reference is None for record in inventory.records)


def test_catalog_identifies_external_transfers() -> None:
    inventory = build_default_privacy_inventory()
    external = {
        record.record_id
        for record in inventory.records
        if record.international_transfer
    }
    assert external == {
        "internet.search_queries",
        "school.crm_leads",
        "voice.neural_tts_and_cache",
        "voice.speech_recognition",
    }


def test_catalog_identifies_children_data_flows() -> None:
    inventory = build_default_privacy_inventory()
    child_records = {
        record.record_id
        for record in inventory.records
        if DataSubject.CHILD_OR_ADOLESCENT in record.subjects
    }
    assert child_records == {
        "core.conversation_context",
        "privacy.incident_response_records",
        "privacy.retention_disposal_actions",
        "privacy.subject_rights_requests",
        "school.crm_leads",
        "vision.screen_capture",
    }


def test_catalog_does_not_claim_storage_encryption() -> None:
    inventory = build_default_privacy_inventory()
    persistent_local = [
        store
        for record in inventory.records
        for store in record.stores
        if store.local and not store.ephemeral
    ]
    assert persistent_local
    assert all(store.encrypted_at_rest is not True for store in persistent_local)


def test_catalog_locations_never_contain_secret_values() -> None:
    inventory = build_default_privacy_inventory()
    locations = "\n".join(
        store.location
        for record in inventory.records
        for store in record.stores
    ).casefold()
    assert "bearer " not in locations
    assert "whatsapp_access_token=" not in locations
    assert "api_key=" not in locations


def test_catalog_preserves_existing_safe_defaults() -> None:
    inventory = build_default_privacy_inventory()
    memory = inventory.get("memory.long_term_and_embeddings")
    vision = inventory.get("vision.screen_capture")
    school = inventory.get("school.crm_leads")
    edge = inventory.get("edge.device_and_employee_onboarding")
    assert "sensitive_auto_memory_off" in memory.implemented_controls
    assert "transient_by_default" in vision.implemented_controls
    assert "dry_run_default" in school.implemented_controls
    assert "human_confirmation" in edge.implemented_controls


def test_catalog_exposes_current_retention_gaps() -> None:
    inventory = build_default_privacy_inventory()
    undefined = {
        record.record_id
        for record in inventory.records
        if record.retention.mode is RetentionMode.UNDEFINED
    }
    assert {
        "edge.device_and_employee_onboarding",
        "logs.application_diagnostics",
        "memory.long_term_and_embeddings",
        "scheduler.jobs",
        "session.operational_history",
    }.issubset(undefined)


def test_catalog_report_has_no_low_risk_false_assurance() -> None:
    report = build_default_privacy_inventory().analyze()
    assert report.total_records == 19
    assert report.counts_by_nature[DataNature.SENSITIVE_PERSONAL.value] >= 3
    assert report.counts_by_risk[RiskLevel.CRITICAL.value] >= 2
    assert report.requires_action is True
    assert report.high_or_critical_issues > 0


def test_sprint24_stage1_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "privacy_inventory_pilot.py").is_file()
    assert (root / "docs" / "SPRINT24_ETAPA1_INVENTARIO_DADOS.md").is_file()
    assert (root / "docs" / "SPRINT24_ETAPA1_VALIDACAO.md").is_file()
