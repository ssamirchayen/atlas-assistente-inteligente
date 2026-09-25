"""Teste opcional contra o código real do CRM, usando somente banco em memória.

Defina NEXYRA_CRM_SOURCE para a pasta que contém app/ do CRM.
Requer as dependências de testes do CRM no mesmo ambiente Python.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests

from atlas.integrations.nexyra_crm import (
    NexyraActionRequest,
    NexyraClient,
    NexyraConfig,
    NexyraError,
)
from atlas.integrations.nexyra_crm.commands import format_response

pytestmark = pytest.mark.skipif(
    not os.getenv("NEXYRA_CRM_SOURCE"),
    reason="NEXYRA_CRM_SOURCE não configurado",
)


@pytest.fixture
def real_crm(monkeypatch):
    crm = Path(os.environ["NEXYRA_CRM_SOURCE"]).resolve()
    assert (crm / "app" / "integrations" / "atlas").is_dir()
    monkeypatch.syspath_prepend(str(crm))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ATLAS_INTEGRATION_TOKEN", "integration-test-only")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.api.routes.atlas_integration import router
    from app.core.config import get_settings
    from app.db import Base, get_db
    from app.models import (
        Activity,
        Lead,
        Opportunity,
        User,
        Workspace,
        WorkspaceMembership,
    )

    get_settings.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        workspace = Workspace(
            name="Empresa contrato", slug="contrato", segment="education"
        )
        other = Workspace(name="Outra empresa", slug="outra", segment="generic")
        user = User(name="Consultor contrato", email="test@example.invalid")
        admin = User(name="Admin contrato", email="admin@example.invalid")
        db.add_all([workspace, other, user, admin])
        db.flush()
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id, user_id=user.id, role="seller"
            )
        )
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id, user_id=admin.id, role="admin"
            )
        )
        lead = Lead(
            workspace_id=workspace.id,
            name="Lead sintético",
            source="instagram",
            channel="lead_ads",
        )
        db.add(lead)
        db.flush()
        db.add(
            Opportunity(
                workspace_id=workspace.id,
                lead_id=lead.id,
                title="Venda sintética",
                stage="ganho",
                status="won",
                value_amount=150,
            )
        )
        db.add_all(
            [
                Activity(
                    workspace_id=workspace.id,
                    title=f"Retorno {i}",
                    activity_type="followup",
                )
                for i in range(30)
            ]
        )
        db.commit()
        config = NexyraConfig(
            "http://127.0.0.1:8000",
            "integration-test-only",
            workspace.public_id,
            user.public_id,
        )
        admin_config = NexyraConfig(
            "http://127.0.0.1:8000",
            "integration-test-only",
            workspace.public_id,
            admin.public_id,
        )
        other_id = other.public_id
        lead_id = lead.public_id

    def database():
        with Session(engine) as db:
            yield db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = database
    with TestClient(app) as http:

        def get(session, url, **kwargs):
            del session
            return http.get(
                urlsplit(url).path,
                headers=kwargs["headers"],
                follow_redirects=kwargs["allow_redirects"],
            )

        def post(session, url, **kwargs):
            del session
            return http.post(
                urlsplit(url).path,
                headers=kwargs["headers"],
                json=kwargs["json"],
                follow_redirects=kwargs["allow_redirects"],
            )

        monkeypatch.setattr(requests.Session, "get", get)
        monkeypatch.setattr(requests.Session, "post", post)
        try:
            yield config, admin_config, other_id, lead_id
        finally:
            app.dependency_overrides.clear()
            get_settings.cache_clear()
            engine.dispose()


def test_real_read_contract_and_limit(real_crm):
    config, _, _, _ = real_crm
    data = NexyraClient(config).snapshot()
    context = data["context"]
    assert context["counts"]["leads"] == 1
    assert context["counts"]["pending_followups"] == 30
    assert len(context["pending_followups"]) == 25
    assert context["opportunity_metrics"]["conversion_rate"] == 100
    assert context["actor"]["role"] == "seller"
    assert "atlas.execute" not in context["actor"]["permissions"]
    assert "30. Exibindo 25" in format_response("pending", data)
    assert "instagram / lead_ads: 1 leads ativos" in format_response("sources", data)


def test_real_contract_denies_bad_token(real_crm):
    config, _, _, _ = real_crm
    with pytest.raises(NexyraError) as caught:
        NexyraClient(replace(config, token="wrong")).snapshot()
    assert caught.value.code == "unauthorized"


def test_real_contract_denies_other_company(real_crm):
    config, _, other_id, _ = real_crm
    with pytest.raises(NexyraError) as caught:
        NexyraClient(replace(config, workspace_id=other_id)).snapshot()
    assert caught.value.code == "forbidden"


def test_real_contract_denies_unknown_user(real_crm):
    config, _, _, _ = real_crm
    with pytest.raises(NexyraError) as caught:
        NexyraClient(replace(config, actor_user_id="USR-UNKNOWN")).snapshot()
    assert caught.value.code == "forbidden"


def test_real_action_preview_revalidation_and_execution(real_crm):
    seller, admin, _, lead_id = real_crm
    request = NexyraActionRequest(
        "lead.update", lead_id, {"status": "contatado"}, "teste supervisionado"
    )
    seller_client = NexyraClient(seller)
    preview = seller_client.preview_action(request)
    assert preview.allowed is True
    assert preview.confirmation_required is True
    assert preview.normalized_payload == {"status": "contatado"}

    with pytest.raises(NexyraError) as seller_error:
        seller_client.execute_action(preview)
    assert seller_error.value.code == "forbidden"

    admin_client = NexyraClient(admin)
    admin_preview = admin_client.preview_action(request)
    result = admin_client.execute_action(admin_preview)
    assert result["executed"] is True
    assert result["result"]["status"] == "contatado"


def test_real_operational_intelligence_contract(real_crm):
    seller, admin, _, _ = real_crm

    with pytest.raises(NexyraError) as denied:
        NexyraClient(seller).operations()
    assert denied.value.code == "forbidden"

    data = NexyraClient(admin).operations()
    assert data["contract_version"] == "1.0"
    assert data["distribution"]["total_active_leads"] == 1
    assert data["recommendations"]["metrics"]["total_leads"] == 1
    assert "sla_breached" in data["sla"]["metrics"]
    assert data["dashboard"]["active_leads"] == 1


def test_real_supervised_operational_action_contract(real_crm):
    seller, admin, _, lead_id = real_crm
    seller_client = NexyraClient(seller)
    admin_client = NexyraClient(admin)

    with pytest.raises(NexyraError) as denied:
        seller_client.preview_action(
            NexyraActionRequest(
                "lead.assign",
                lead_id,
                {"user_public_id": seller.actor_user_id},
            )
        )
    assert denied.value.code == "forbidden"

    preview = admin_client.preview_action(
        NexyraActionRequest(
            "lead.prioritize",
            lead_id,
            {"priority": "urgente"},
            "SLA operacional",
        )
    )
    assert preview.normalized_payload == {"priority": "urgente"}
    result = admin_client.execute_action(preview)
    assert result["executed"] is True
    assert result["result"]["priority"] == "urgente"
