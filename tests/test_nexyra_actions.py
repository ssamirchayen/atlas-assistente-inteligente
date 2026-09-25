from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from atlas.integrations.nexyra_crm.client import (
    NexyraActionPreview,
    NexyraActionRequest,
    NexyraClient,
    NexyraConfig,
    NexyraError,
)
from atlas.integrations.nexyra_crm.commands import (
    NexyraPendingAction,
    execute_pending_action,
    format_action_preview,
    parse_action_request,
)
from atlas.memory.database import MemoryStore
from atlas.skills.router import SkillRouter

CONFIG = NexyraConfig(
    "http://127.0.0.1:8000",
    "test-only-secret",
    "company-1",
    "user-1",
)
PREVIEW = {
    "contract_version": "1.0",
    "action": "lead.update",
    "target_public_id": "LEAD-1",
    "allowed": True,
    "confirmation_required": True,
    "summary": "Atualizar lead LEAD-1.",
    "normalized_payload": {"status": "contatado"},
}
EXECUTION = {
    "contract_version": "1.0",
    "action": "lead.update",
    "target_public_id": "LEAD-1",
    "executed": True,
    "result": {"public_id": "LEAD-1", "status": "contatado"},
}


def response(payload: dict, status_code: int = 200) -> Mock:
    item = Mock(status_code=status_code)
    item.json.return_value = payload
    return item


def test_preview_revalidates_and_binds_exact_action_before_execute(monkeypatch):
    post = Mock(
        side_effect=[
            response(PREVIEW),
            response(PREVIEW),
            response(EXECUTION),
        ]
    )
    monkeypatch.setattr(requests.Session, "post", post)
    client = NexyraClient(CONFIG)

    preview = client.preview_action(
        NexyraActionRequest(
            "lead.update",
            "LEAD-1",
            {"status": "contatado"},
            "retorno comercial",
        )
    )
    result = client.execute_action(preview)

    assert result == EXECUTION
    assert post.call_count == 3
    preview_call = post.call_args_list[0]
    revalidation_call = post.call_args_list[1]
    execution_call = post.call_args_list[2]
    assert preview_call.args[0].endswith("/actions/preview")
    assert revalidation_call.args[0].endswith("/actions/preview")
    assert execution_call.args[0].endswith("/actions/execute")
    assert execution_call.kwargs["json"] == {
        "action": "lead.update",
        "target_public_id": "LEAD-1",
        "payload": {"status": "contatado"},
        "reason": "retorno comercial",
        "confirmed": True,
    }


def test_changed_revalidation_aborts_without_execute(monkeypatch):
    changed = dict(PREVIEW, summary="Atualizar outro estado.")
    post = Mock(side_effect=[response(PREVIEW), response(changed)])
    monkeypatch.setattr(requests.Session, "post", post)
    preview = NexyraClient(CONFIG).preview_action(
        NexyraActionRequest("lead.update", "LEAD-1", {"status": "contatado"})
    )

    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).execute_action(preview)

    assert caught.value.code == "preview_changed"
    assert post.call_count == 2


def test_execute_requires_authorized_preview_without_network(monkeypatch):
    post = Mock()
    monkeypatch.setattr(requests.Session, "post", post)
    request = NexyraActionRequest("lead.update", "LEAD-1", {"status": "novo"})
    preview = NexyraActionPreview(
        request=request,
        contract_version="1.0",
        action="lead.update",
        target_public_id="LEAD-1",
        allowed=False,
        confirmation_required=True,
        summary="bloqueada",
        normalized_payload={"status": "novo"},
        fingerprint="x",
    )

    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).execute_action(preview)

    assert caught.value.code == "confirmation_required"
    post.assert_not_called()


@pytest.mark.parametrize(
    "status,code", [(401, "unauthorized"), (409, "conflict"), (500, "server_error")]
)
def test_action_http_errors_are_safe(monkeypatch, status, code):
    post = Mock(return_value=response({}, status))
    monkeypatch.setattr(requests.Session, "post", post)
    with pytest.raises(NexyraError) as caught:
        NexyraClient(CONFIG).preview_action(
            NexyraActionRequest("lead.update", "LEAD-1", {"status": "novo"})
        )
    assert caught.value.code == code
    assert CONFIG.token not in str(caught.value)


@pytest.mark.parametrize(
    "command,action,target,payload,reason",
    [
        (
            'Nexyra prévia lead.update LEAD-1 {"status":"contatado"}; motivo: retorno',
            "lead.update",
            "LEAD-1",
            {"status": "contatado"},
            "retorno",
        ),
        (
            'Nexyra preview opportunity.move OPP-2 {"to_stage":"qualificado"}',
            "opportunity.move",
            "OPP-2",
            {"to_stage": "qualificado"},
            None,
        ),
        (
            'Nexyra simular activity.create {"title":"Ligar","activity_type":"call"}',
            "activity.create",
            None,
            {"title": "Ligar", "activity_type": "call"},
            None,
        ),
        (
            "Nexyra prévia activity.complete ACT-3",
            "activity.complete",
            "ACT-3",
            {},
            None,
        ),
    ],
)
def test_explicit_action_parser_preserves_json(
    command, action, target, payload, reason
):
    request = parse_action_request(command)
    assert request is not None
    assert request.action == action
    assert request.target_public_id == target
    assert request.payload == payload
    assert request.reason == reason


def test_malformed_action_is_rejected_without_network():
    with pytest.raises(NexyraError, match="objeto JSON"):
        parse_action_request("Nexyra prévia lead.update LEAD-1 status=novo")


def test_router_requires_confirmation_and_clears_pending_on_success(
    tmp_path: Path,
    monkeypatch,
):
    post = Mock(
        side_effect=[
            response(PREVIEW),
            response(PREVIEW),
            response(EXECUTION),
        ]
    )
    monkeypatch.setattr(requests.Session, "post", post)
    monkeypatch.setenv("ATLAS_NEXYRA_URL", CONFIG.base_url)
    monkeypatch.setenv("ATLAS_NEXYRA_TOKEN", CONFIG.token)
    monkeypatch.setenv("ATLAS_NEXYRA_WORKSPACE_ID", CONFIG.workspace_id)
    monkeypatch.setenv("ATLAS_NEXYRA_ACTOR_USER_ID", CONFIG.actor_user_id)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        preview = router.route_priority(
            'Nexyra prévia lead.update LEAD-1 {"status":"contatado"}'
        )
        assert preview.handled and preview.needs_followup
        assert "nada foi alterado" in preview.message
        assert post.call_count == 1

        waiting = router.route("talvez")
        assert waiting.needs_followup and post.call_count == 1
        completed = router.route("sim")
        assert completed.handled and "executada com sucesso" in completed.message
        assert post.call_count == 3
        assert router.pending_nexyra_action is None

        no_pending = router.route_priority("Nexyra executar")
        assert (
            no_pending.handled and "Não há ação Nexyra pendente" in no_pending.message
        )
        assert post.call_count == 3
    finally:
        memory.close()


def test_action_failure_does_not_leave_retry_state(tmp_path: Path, monkeypatch):
    post = Mock(side_effect=[response(PREVIEW), response(PREVIEW, 500)])
    monkeypatch.setattr(requests.Session, "post", post)
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
        router.route_priority('Nexyra prévia lead.update LEAD-1 {"status":"contatado"}')
        result = router.route("sim")
        assert "não foi executada" in result.message
        assert router.pending_nexyra_action is None
    finally:
        memory.close()


def test_action_formatters_are_explicit():
    preview = NexyraActionPreview(
        request=NexyraActionRequest("lead.update", "LEAD-1", {"status": "novo"}),
        contract_version="1.0",
        action="lead.update",
        target_public_id="LEAD-1",
        allowed=True,
        confirmation_required=True,
        summary="Atualizar lead LEAD-1.",
        normalized_payload={"status": "novo"},
        fingerprint="x",
    )
    assert "Responda 'sim'" in format_action_preview(
        NexyraPendingAction(preview, Mock())
    )


def _configure_nexyra_env(monkeypatch) -> None:
    for name, value in {
        "URL": CONFIG.base_url,
        "TOKEN": CONFIG.token,
        "WORKSPACE_ID": CONFIG.workspace_id,
        "ACTOR_USER_ID": CONFIG.actor_user_id,
    }.items():
        monkeypatch.setenv("ATLAS_NEXYRA_" + name, value)


def test_priority_router_intercepts_nexyra_confirmation_before_planner(
    tmp_path: Path,
    monkeypatch,
):
    post = Mock(
        side_effect=[
            response(PREVIEW),
            response(PREVIEW),
            response(EXECUTION),
        ]
    )
    monkeypatch.setattr(requests.Session, "post", post)
    _configure_nexyra_env(monkeypatch)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        preview = router.route_priority(
            'Nexyra prévia lead.update LEAD-1 {"status":"contatado"}'
        )
        assert preview.needs_followup

        # Esta é a rota chamada antes do Planner pela GUI/loop principal.
        completed = router.route_priority("sim")

        assert completed.handled
        assert "executada com sucesso" in completed.message
        assert router.pending_nexyra_action is None
        assert post.call_count == 3
    finally:
        memory.close()


def test_pending_preview_blocks_a_different_nexyra_action(
    tmp_path: Path,
    monkeypatch,
):
    post = Mock(return_value=response(PREVIEW))
    monkeypatch.setattr(requests.Session, "post", post)
    _configure_nexyra_env(monkeypatch)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        router.route_priority(
            'Nexyra prévia lead.update LEAD-1 {"status":"contatado"}'
        )

        blocked = router.route_priority(
            'Nexyra prévia lead.update LEAD-2 {"status":"novo"}'
        )

        assert blocked.handled and blocked.needs_followup
        assert "aguardando confirmação" in blocked.message
        assert post.call_count == 1
        assert router.pending_nexyra_action is not None
        assert router.pending_nexyra_action.preview.target_public_id == "LEAD-1"
    finally:
        memory.close()


def test_expired_preview_is_cleared_without_execution(
    tmp_path: Path,
    monkeypatch,
):
    post = Mock(return_value=response(PREVIEW))
    monkeypatch.setattr(requests.Session, "post", post)
    _configure_nexyra_env(monkeypatch)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        router.route_priority(
            'Nexyra prévia lead.update LEAD-1 {"status":"contatado"}'
        )
        pending = router.pending_nexyra_action
        assert pending is not None
        router.pending_nexyra_action = NexyraPendingAction(
            pending.preview,
            pending.client,
            created_at=pending.created_at - 121,
        )

        result = router.route_priority("sim")

        assert result.handled
        assert "expirou após 2 minutos" in result.message
        assert router.pending_nexyra_action is None
        assert post.call_count == 1
    finally:
        memory.close()


@pytest.mark.parametrize(
    "command",
    ["não", "cancelar", "Nexyra cancelar", "cancelar Nexyra", "Nexyra limpar"],
)
def test_cancel_aliases_invalidate_pending_preview(
    tmp_path: Path,
    monkeypatch,
    command: str,
):
    post = Mock(return_value=response(PREVIEW))
    monkeypatch.setattr(requests.Session, "post", post)
    _configure_nexyra_env(monkeypatch)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        router.route_priority(
            'Nexyra prévia lead.update LEAD-1 {"status":"contatado"}'
        )
        cancelled = router.route_priority(command)

        assert cancelled.handled
        assert "cancelada" in cancelled.message
        assert router.pending_nexyra_action is None
        assert post.call_count == 1
    finally:
        memory.close()


def test_direct_execution_refuses_expired_pending_without_network():
    client = Mock()
    preview = NexyraActionPreview(
        request=NexyraActionRequest("lead.update", "LEAD-1", {"status": "novo"}),
        contract_version="1.0",
        action="lead.update",
        target_public_id="LEAD-1",
        allowed=True,
        confirmation_required=True,
        summary="Atualizar lead LEAD-1.",
        normalized_payload={"status": "novo"},
        fingerprint="x",
    )
    pending = NexyraPendingAction(preview, client, created_at=-1_000_000)

    message = execute_pending_action(pending)

    assert "expirou após 2 minutos" in message
    client.execute_action.assert_not_called()


def test_timeout_after_execute_attempt_clears_state_and_never_retries(
    tmp_path: Path,
    monkeypatch,
):
    post = Mock(
        side_effect=[
            response(PREVIEW),
            response(PREVIEW),
            requests.Timeout("synthetic timeout after send"),
        ]
    )
    monkeypatch.setattr(requests.Session, "post", post)
    _configure_nexyra_env(monkeypatch)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        router.route_priority(
            'Nexyra prévia lead.update LEAD-1 {"status":"contatado"}'
        )

        result = router.route_priority("sim")

        assert result.handled
        assert "não foi executada" in result.message
        assert "confira o CRM" in result.message
        assert router.pending_nexyra_action is None
        assert post.call_count == 3

        # Um segundo "sim" não dispara repetição da escrita incerta.
        no_retry = router.route_priority("sim")
        assert not no_retry.handled
        assert post.call_count == 3
    finally:
        memory.close()


@pytest.mark.parametrize(
    "command,action,target,payload",
    [
        (
            "Nexyra prévia atribuir LEAD-10 USER-20",
            "lead.assign",
            "LEAD-10",
            {"user_public_id": "USER-20"},
        ),
        (
            "Nexyra prévia priorizar LEAD-10 urgente",
            "lead.prioritize",
            "LEAD-10",
            {"priority": "urgente"},
        ),
        (
            "Nexyra prévia retorno LEAD-10 2099-09-20T14:00:00+00:00",
            "lead.followup",
            "LEAD-10",
            {"due_at": "2099-09-20T14:00:00+00:00"},
        ),
        (
            "Nexyra prévia distribuir 25",
            "distribution.run",
            None,
            {"limit": 25},
        ),
        (
            "Nexyra prévia distribuir fila 10",
            "distribution.run",
            None,
            {"limit": 10},
        ),
    ],
)
def test_operational_action_aliases(command, action, target, payload):
    request = parse_action_request(command)
    assert request is not None
    assert request.action == action
    assert request.target_public_id == target
    assert request.payload == payload


def test_distribution_action_accepts_no_target_and_revalidates(monkeypatch):
    preview_payload = {
        "contract_version": "1.0",
        "action": "distribution.run",
        "target_public_id": None,
        "allowed": True,
        "confirmation_required": True,
        "summary": "Distribuir 2 lead(s) pela configuração ativa.",
        "normalized_payload": {
            "limit": 25,
            "expected_assignments": [
                {"lead_public_id": "LEAD-1", "user_public_id": "USER-1"},
                {"lead_public_id": "LEAD-2", "user_public_id": "USER-2"},
            ],
        },
    }
    execution = {
        "contract_version": "1.0",
        "action": "distribution.run",
        "target_public_id": None,
        "executed": True,
        "result": {"scanned": 2, "assigned": 2, "skipped": 0, "assignments": []},
    }
    post = Mock(
        side_effect=[
            response(preview_payload),
            response(preview_payload),
            response(execution),
        ]
    )
    monkeypatch.setattr(requests.Session, "post", post)
    client = NexyraClient(CONFIG)

    preview = client.preview_action(
        NexyraActionRequest("distribution.run", None, {"limit": 25})
    )
    result = client.execute_action(preview)

    assert result["executed"] is True
    assert post.call_count == 3
    assert post.call_args_list[2].kwargs["json"]["payload"][
        "expected_assignments"
    ] == preview_payload["normalized_payload"]["expected_assignments"]


def test_operational_action_preview_still_requires_confirmation(
    tmp_path: Path,
    monkeypatch,
):
    operational_preview = {
        "contract_version": "1.0",
        "action": "lead.prioritize",
        "target_public_id": "LEAD-20",
        "allowed": True,
        "confirmation_required": True,
        "summary": "Alterar prioridade do lead LEAD-20 de media para urgente.",
        "normalized_payload": {"priority": "urgente"},
    }
    operational_execution = {
        "contract_version": "1.0",
        "action": "lead.prioritize",
        "target_public_id": "LEAD-20",
        "executed": True,
        "result": {"public_id": "LEAD-20", "priority": "urgente"},
    }
    post = Mock(
        side_effect=[
            response(operational_preview),
            response(operational_preview),
            response(operational_execution),
        ]
    )
    monkeypatch.setattr(requests.Session, "post", post)
    _configure_nexyra_env(monkeypatch)
    memory = MemoryStore(tmp_path / "memory.db", semantic_enabled=False)
    try:
        router = SkillRouter(memory)
        preview = router.route_priority(
            "Nexyra prévia priorizar LEAD-20 urgente"
        )
        assert preview.handled
        assert preview.needs_followup
        assert post.call_count == 1

        done = router.route_priority("sim")
        assert done.handled
        assert "executada com sucesso" in done.message
        assert post.call_count == 3
    finally:
        memory.close()
