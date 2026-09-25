from __future__ import annotations

import copy
from dataclasses import replace
from unittest.mock import Mock

import pytest
import requests

from atlas.integrations.nexyra_crm.client import (
    API_PREFIX,
    NexyraClient,
    NexyraConfig,
    NexyraError,
)
from atlas.integrations.nexyra_crm.commands import handle_command, parse_command
from atlas.integrations.nexyra_crm.connector import NexyraApiDriver, NexyraConnector

CONFIG = NexyraConfig(
    "http://127.0.0.1:8000", "test-only-secret", "company-1", "user-1"
)
HEALTH = {
    "ok": True,
    "product": "Nexyra CRM",
    "crm_version": "1.0.0",
    "contract_name": "nexyra-crm-atlas",
    "contract_version": "1.0",
}
CAPABILITIES = {
    "contract_name": "nexyra-crm-atlas",
    "contract_version": "1.0",
    "capabilities": ["workspace_context"],
    "supported_actions": ["lead.update"],
    "confirmation_required_for_execution": True,
    "supported_actor_types": ["user", "atlas"],
}
CONTEXT = {
    "contract_version": "1.0",
    "workspace": {"public_id": "company-1", "name": "Escola de teste", "active": True},
    "actor": {
        "user_public_id": "user-1",
        "name": "Consultor",
        "role": "seller",
        "permissions": ["atlas.use"],
    },
    "segment": {},
    "members": [],
    "counts": {
        "leads": 9,
        "active_leads": 8,
        "opportunities": 5,
        "pending_followups": 31,
    },
    "opportunity_metrics": {
        "total_opportunities": 5,
        "open_opportunities": 2,
        "won_opportunities": 2,
        "lost_opportunities": 1,
        "conversion_rate": 66.67,
        "total_pipeline_value": "1000.25",
        "won_value": "500.00",
        "average_won_value": "250.00",
    },
    "lead_sources": [{"source": "instagram", "channel": "lead_ads", "lead_count": 8}],
    "pending_followups": [
        {
            "public_id": f"act-{i}",
            "title": f"Retorno {i}",
            "due_at": None,
            "overdue": False,
        }
        for i in range(25)
    ],
}


@pytest.fixture
def transport(monkeypatch):
    payloads = copy.deepcopy([HEALTH, CAPABILITIES, CONTEXT])
    calls = []

    def get(session, url, **kwargs):
        calls.append((url, kwargs))
        assert session.trust_env is False
        index = {"/health": 0, "/capabilities": 1, "/workspaces/company-1/context": 2}[
            url.split(API_PREFIX)[1]
        ]
        response = Mock(status_code=200)
        response.json.return_value = payloads[index]
        return response

    monkeypatch.setattr(requests.Session, "get", get)
    return payloads, calls


def test_contract_headers_identity_and_no_redirect(transport):
    _, calls = transport
    data = NexyraClient(CONFIG).snapshot()
    assert data["context"]["workspace"]["public_id"] == CONFIG.workspace_id
    assert len(calls) == 3
    assert "X-Nexyra-Integration-Token" not in calls[0][1]["headers"]
    for _, kwargs in calls[1:]:
        assert kwargs["headers"]["X-Nexyra-Integration-Token"] == CONFIG.token
        assert kwargs["headers"]["X-Nexyra-Actor-User"] == CONFIG.actor_user_id
        assert kwargs["timeout"] == 10
        assert kwargs["allow_redirects"] is False


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (422, "invalid_request"),
        (429, "rate_limited"),
        (500, "server_error"),
        (302, "redirect"),
    ],
)
def test_http_errors_do_not_expose_body_or_token(monkeypatch, status, code):
    response = Mock(status_code=status, text=CONFIG.token)
    monkeypatch.setattr(requests.Session, "get", Mock(return_value=response))
    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).health()
    assert caught.value.code == code
    assert CONFIG.token not in str(caught.value)
    response.json.assert_not_called()


@pytest.mark.parametrize(
    "error,code",
    [
        (requests.Timeout("secret"), "timeout"),
        (requests.ConnectionError("secret"), "unavailable"),
    ],
)
def test_network_errors_do_not_repeat(monkeypatch, error, code):
    get = Mock(side_effect=error)
    monkeypatch.setattr(requests.Session, "get", get)
    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).snapshot()
    assert caught.value.code == code
    assert "secret" not in str(caught.value)
    assert get.call_count == 1


@pytest.mark.parametrize("body", [[], None, "<html>", 123])
def test_non_object_response(monkeypatch, body):
    response = Mock(status_code=200)
    response.json.return_value = body
    monkeypatch.setattr(requests.Session, "get", Mock(return_value=response))
    with pytest.raises(NexyraError, match="incompatíveis"):
        NexyraClient(CONFIG).health()


def test_invalid_json(monkeypatch):
    response = Mock(status_code=200)
    response.json.side_effect = ValueError("private body")
    monkeypatch.setattr(requests.Session, "get", Mock(return_value=response))
    with pytest.raises(NexyraError, match="incompatíveis"):
        NexyraClient(CONFIG).health()


@pytest.mark.parametrize(
    "index,key,value,code",
    [
        (0, "contract_version", "2.0", "incompatible_contract"),
        (1, "contract_name", "other", "incompatible_contract"),
        (2, "contract_version", "1.1", "incompatible_contract"),
        (0, "ok", False, "unhealthy"),
        (1, "capabilities", [], "missing_capability"),
        (2, "counts", {}, "invalid_response"),
        (2, "opportunity_metrics", {}, "invalid_response"),
        (2, "pending_followups", [None], "invalid_response"),
        (2, "lead_sources", [{"source": "x"}], "invalid_response"),
    ],
)
def test_contract_failure_stops_query(transport, index, key, value, code):
    payloads, calls = transport
    payloads[index][key] = value
    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).snapshot()
    assert caught.value.code == code
    assert len(calls) == index + 1


@pytest.mark.parametrize(
    "section,key,value,code",
    [
        ("workspace", "public_id", "another-company", "identity_mismatch"),
        ("actor", "user_public_id", "another-user", "identity_mismatch"),
        ("actor", "permissions", [], "forbidden"),
        ("workspace", "active", False, "inactive_workspace"),
        ("opportunity_metrics", "won_value", "NaN", "invalid_response"),
        ("counts", "leads", True, "invalid_response"),
    ],
)
def test_context_validation(transport, section, key, value, code):
    payloads, _ = transport
    payloads[2][section][key] = value
    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).snapshot()
    assert caught.value.code == code


@pytest.mark.parametrize(
    "changes",
    [
        {"base_url": ""},
        {"token": ""},
        {"workspace_id": "../other"},
        {"actor_user_id": "a\r\nb"},
        {"token": "x\ny"},
        {"base_url": "https://example.com/api/v1"},
        {"base_url": "https://user:pass@example.com"},
        {"base_url": "https://example.com?token=abc"},
        {"base_url": "http://example.com"},
        {"timeout": 0},
        {"timeout": float("nan")},
        {"timeout": 61},
    ],
)
def test_bad_configuration_never_connects(monkeypatch, changes):
    get = Mock()
    monkeypatch.setattr(requests.Session, "get", get)
    with pytest.raises(NexyraError):
        NexyraClient(replace(CONFIG, **changes))
    get.assert_not_called()
    assert CONFIG.token not in repr(CONFIG)


def test_empty_env_is_clear_and_lazy(monkeypatch):
    for name in ("URL", "TOKEN", "WORKSPACE_ID", "ACTOR_USER_ID", "TIMEOUT"):
        monkeypatch.delenv("ATLAS_NEXYRA_" + name, raising=False)
    connector = NexyraConnector()
    result = connector.execute("diagnose")
    assert not result.ok
    assert "ATLAS_NEXYRA_TOKEN" in result.error


@pytest.mark.parametrize(
    "command,expected",
    [
        ("Nexyra diagnóstico", "diagnose"),
        ("Nexyra resumo comercial", "summary"),
        ("Por favor Nexyra pendências", "pending"),
        ("indicadores do Nexyra", "metrics"),
        ("Nexyra fontes", "sources"),
        ("Nexyra apagar lead", "help"),
        ("lembre que trabalho na Nexyra", None),
        ("abrir calculadora", None),
        ("o que é Nexyra", None),
    ],
)
def test_explicit_commands(command, expected):
    assert parse_command(command) == expected


def test_pending_limit_and_company_scope_are_visible(transport):
    output = handle_command("Nexyra pendências", NexyraApiDriver(NexyraClient(CONFIG)))
    assert "31. Exibindo 25" in output
    assert "não apenas do usuário" in output
    assert "act-24" in output


def test_metrics_use_crm_denominator_and_no_assumed_currency(transport):
    output = handle_command("Nexyra indicadores", NexyraApiDriver(NexyraClient(CONFIG)))
    assert "encerradas: 66,67%" in output
    assert "1.000,25" in output
    assert "não informa a moeda" in output
    assert "sem filtro de período" in output


def test_no_network_for_writes_or_unrelated_commands():
    driver = Mock()
    assert handle_command("bom dia", driver) is None
    message = handle_command("Nexyra excluir lead", driver)
    assert message is not None
    assert "Ações supervisionadas" in message
    assert "prévia" in message
    driver.execute.assert_not_called()
    result = NexyraApiDriver().execute("lead.update")
    assert not result.ok


def test_router_priority_returns_crm_reply_before_memory(
    tmp_path, monkeypatch, transport
):
    from atlas.memory.database import MemoryStore
    from atlas.skills.router import SkillRouter

    for name, value in {
        "URL": CONFIG.base_url,
        "TOKEN": CONFIG.token,
        "WORKSPACE_ID": CONFIG.workspace_id,
        "ACTOR_USER_ID": CONFIG.actor_user_id,
    }.items():
        monkeypatch.setenv("ATLAS_NEXYRA_" + name, value)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        result = router.route_priority("Nexyra resumo")
        assert result.handled and "Leads: 9" in result.message
        assert not memory.list_records()
    finally:
        memory.close()

OPERATIONS = {
    "contract_version": "1.0",
    "generated_at": "2026-09-18T12:00:00+00:00",
    "distribution": {
        "enabled": True,
        "strategy": "round_robin",
        "total_active_leads": 12,
        "unassigned_active_leads": 2,
        "members": [
            {
                "user_public_id": "user-1",
                "name": "Consultor A",
                "role": "seller",
                "eligible": True,
                "assigned_active_leads": 7,
            },
            {
                "user_public_id": "user-2",
                "name": "Consultor B",
                "role": "seller",
                "eligible": True,
                "assigned_active_leads": 3,
            },
        ],
    },
    "sla": {
        "config": {},
        "metrics": {
            "total_attention": 5,
            "awaiting_first_contact": 3,
            "sla_warning": 1,
            "sla_breached": 2,
            "overdue_followups": 2,
            "due_soon_followups": 1,
            "stale_leads": 2,
            "unassigned": 2,
        },
        "items": [
            {
                "lead_public_id": "lead-1",
                "lead_name": "Lead crítico",
                "status": "novo",
                "priority": "urgente",
                "source": "instagram",
                "owner_user_public_id": None,
                "owner_name": None,
                "sla_state": "breached",
                "age_minutes": 120,
                "overdue_followups": 1,
                "stale": True,
                "score": 95,
                "reasons": ["SLA de primeiro contato estourada"],
            }
        ],
    },
    "recommendations": {
        "generated_at": "2026-09-18T12:00:00+00:00",
        "suggested_contact_window": None,
        "metrics": {
            "total_leads": 12,
            "critical": 1,
            "high": 2,
            "medium": 4,
            "low": 5,
            "awaiting_reply": 1,
            "overdue_followups": 2,
            "unassigned": 2,
            "opportunities_at_risk": 1,
        },
        "items": [
            {
                "lead_public_id": "lead-1",
                "lead_name": "Lead crítico",
                "interest": "Radiologia",
                "status": "novo",
                "priority": "urgente",
                "source": "instagram",
                "owner_user_public_id": None,
                "owner_name": None,
                "action": "first_contact",
                "action_title": "Fazer primeiro contato",
                "urgency": "critical",
                "score": 95,
                "suggested_channel": "whatsapp",
                "suggested_contact_window": None,
                "reasons": ["SLA estourada"],
                "reason_codes": ["sla_breached"],
                "last_contact_at": None,
                "last_whatsapp_at": None,
                "awaiting_whatsapp_reply": False,
                "active_cadence": False,
                "open_opportunity_public_id": None,
                "open_opportunity_stage": None,
                "open_opportunity_value": None,
                "opportunity_at_risk": False,
            }
        ],
    },
    "dashboard": {
        "workspace_public_id": "company-1",
        "workspace_name": "Escola de teste",
        "generated_at": "2026-09-18T12:00:00+00:00",
        "period_days": 30,
        "period_start": "2026-08-19T12:00:00+00:00",
        "period_end": "2026-09-18T12:00:00+00:00",
        "owner_user_public_id_filter": None,
        "available_members": [],
        "active_leads": 12,
        "leads_created": 9,
        "high_priority_leads": 3,
        "unassigned_leads": 2,
        "open_opportunities": 4,
        "open_pipeline_value": "1000.00",
        "conversion_rate": 40.0,
        "won_value": "500.00",
        "pending_activities": 5,
        "overdue_activities": 2,
        "sla": {
            "total_attention": 5,
            "awaiting_first_contact": 3,
            "warning": 1,
            "breached": 2,
            "overdue_followups": 2,
            "due_soon_followups": 1,
            "stale_leads": 2,
            "attention_share_percent": 41.67,
        },
        "recommendations": {
            "total": 12,
            "critical": 1,
            "high": 2,
            "awaiting_reply": 1,
            "opportunities_at_risk": 1,
        },
        "whatsapp": {},
        "cadences": {},
        "bottlenecks": [
            {
                "code": "sla_breached",
                "title": "SLA estourada",
                "count": 2,
                "severity": "critical",
                "route": "/leads",
            }
        ],
        "pipeline_stages": [],
        "member_performance": [],
    },
}


def test_operational_client_and_commands(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = copy.deepcopy(OPERATIONS)
    get = Mock(return_value=response)
    monkeypatch.setattr(requests.Session, "get", get)

    client = NexyraClient(CONFIG)
    data = client.operations()
    assert data["sla"]["metrics"]["sla_breached"] == 2
    assert "period_days=30&limit=100" in get.call_args.args[0]

    driver = NexyraApiDriver(client)
    assert "SLA estourada: 2" in handle_command("Nexyra fila", driver)
    assert "Lead crítico" in handle_command("Nexyra recomendações", driver)
    assert "Consultor A" in handle_command("Nexyra equipe", driver)
    assert "Oportunidades abertas: 4" in handle_command("Nexyra dashboard", driver)
    assert "Principais gargalos" in handle_command("Nexyra operação", driver)


@pytest.mark.parametrize(
    "command,expected",
    [
        ("Nexyra fila inteligente", "queue"),
        ("Nexyra SLA estourada", "sla"),
        ("Nexyra recomendações", "recommendations"),
        ("Nexyra dashboard", "dashboard"),
        ("Nexyra carga da equipe", "team"),
        ("resuma a operação comercial do Nexyra", "operations"),
        ("quais leads precisam de atenção no Nexyra", "queue"),
        ("quem está com SLA estourada no Nexyra", "sla"),
        ("quais leads eu preciso atender agora", "queue"),
        ("quais vendedores estão sobrecarregados", "team"),
        ("quais oportunidades estão em risco", "recommendations"),
        ("resuma a operação comercial de hoje", "operations"),
    ],
)
def test_operational_command_aliases(command, expected):
    assert parse_command(command) == expected


def test_operational_route_missing_explains_product_split(monkeypatch):
    response = Mock(status_code=404)
    get = Mock(return_value=response)
    monkeypatch.setattr(requests.Session, "get", get)

    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).operations()

    assert caught.value.code == "missing_capability"
    assert "Nexyra + Atlas" in str(caught.value)
    assert "Nexyra padrão" in str(caught.value)
