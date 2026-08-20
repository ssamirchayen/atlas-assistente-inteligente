from __future__ import annotations

from datetime import datetime, timezone

import pytest

from atlas.connectors import (
    ConnectorCapability,
    ConnectorManifest,
    ConnectorOperation,
    ConnectorRegistry,
    ConnectorRisk,
)


def make_manifest(connector_id: str = "school.crm") -> ConnectorManifest:
    return ConnectorManifest(
        connector_id=connector_id,
        display_name="CRM escolar",
        description="Consulta e atualização segura de leads.",
        capabilities=(
            ConnectorCapability(
                name="leads.read",
                required_scope="school.leads:read",
                risk=ConnectorRisk.READ_ONLY,
            ),
            ConnectorCapability(
                name="leads.update",
                required_scope="school.leads:write",
                risk=ConnectorRisk.EXTERNAL_WRITE,
            ),
        ),
        max_batch_size=20,
        operations_per_minute=60,
    )


def test_manifest_normalizes_identity_and_resolves_capability() -> None:
    manifest = make_manifest("  School.CRM ")

    assert manifest.connector_id == "school.crm"
    assert manifest.get_capability(" LEADS.READ ") is not None
    assert manifest.get_capability("leads.missing") is None


def test_manifest_rejects_duplicate_capabilities() -> None:
    duplicate = ConnectorCapability(
        name="leads.read",
        required_scope="school.leads:read",
        risk=ConnectorRisk.READ_ONLY,
    )

    with pytest.raises(ValueError, match="devem ser únicas"):
        ConnectorManifest(
            connector_id="school.crm",
            display_name="CRM",
            description="CRM de teste.",
            capabilities=(duplicate, duplicate),
        )


@pytest.mark.parametrize(
    "connector_id",
    ["", "1connector", "conector com espaço", "conector/externo"],
)
def test_manifest_rejects_invalid_identifier(connector_id: str) -> None:
    with pytest.raises(ValueError, match="identificador"):
        make_manifest(connector_id)


def test_registry_prevents_silent_replacement() -> None:
    registry = ConnectorRegistry((make_manifest(),))

    with pytest.raises(ValueError, match="Já existe"):
        registry.register(make_manifest("SCHOOL.CRM"))


def test_registry_catalog_is_deterministic_and_can_unregister() -> None:
    registry = ConnectorRegistry(
        (
            make_manifest("whatsapp.business"),
            make_manifest("school.crm"),
        )
    )

    assert [item.connector_id for item in registry.catalog()] == [
        "school.crm",
        "whatsapp.business",
    ]
    assert registry.unregister(" SCHOOL.CRM ") is True
    assert registry.unregister("school.crm") is False


def test_registry_resolves_manifest_and_fixed_risk() -> None:
    registry = ConnectorRegistry((make_manifest(),))

    resolved = registry.resolve("school.crm", "leads.update")

    assert resolved is not None
    manifest, capability = resolved
    assert manifest.connector_id == "school.crm"
    assert capability.risk is ConnectorRisk.EXTERNAL_WRITE


def test_operation_freezes_json_parameters_and_has_stable_fingerprint() -> None:
    original = {"lead": {"name": "Ana"}, "tags": ["novo", "escola"]}
    operation = ConnectorOperation(
        connector_id="school.crm",
        capability="leads.update",
        parameters=original,
        operation_id="operation-1",
        idempotency_key="lead-ana-v1",
        created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    fingerprint = operation.fingerprint()
    original["lead"]["name"] = "Alterado"
    original["tags"].append("mutação")

    assert operation.parameters["lead"]["name"] == "Ana"
    assert operation.parameters["tags"] == ("novo", "escola")
    assert operation.fingerprint() == fingerprint


def test_operation_rejects_non_json_or_naive_values() -> None:
    with pytest.raises(TypeError, match="valores JSON"):
        ConnectorOperation(
            connector_id="school.crm",
            capability="leads.read",
            parameters={"invalid": object()},
        )

    with pytest.raises(ValueError, match="fuso horário"):
        ConnectorOperation(
            connector_id="school.crm",
            capability="leads.read",
            created_at=datetime(2026, 8, 20),
        )
