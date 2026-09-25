from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from json import JSONDecodeError

from atlas.utils.text import clean_politeness, normalize

from .client import (
    NexyraActionPreview,
    NexyraActionRequest,
    NexyraClient,
    NexyraConfig,
    NexyraError,
)
from .connector import NexyraApiDriver

_COMMANDS = {
    "diagnostico": "diagnose",
    "status": "diagnose",
    "conexao": "diagnose",
    "resumo": "summary",
    "resumo comercial": "summary",
    "indicadores": "metrics",
    "pendencias": "pending",
    "retornos": "pending",
    "fontes": "sources",
    "origens": "sources",
    "fila": "queue",
    "fila inteligente": "queue",
    "sla": "sla",
    "sla estourada": "sla",
    "recomendacoes": "recommendations",
    "recomendacao": "recommendations",
    "dashboard": "dashboard",
    "painel operacional": "dashboard",
    "equipe": "team",
    "carga da equipe": "team",
    "operacao": "operations",
    "resumo operacional": "operations",
}
HELP = (
    "Consultas disponíveis: 'Nexyra diagnóstico', 'Nexyra resumo', "
    "'Nexyra fila', 'Nexyra SLA', 'Nexyra recomendações', "
    "'Nexyra dashboard', 'Nexyra equipe' e 'Nexyra operação'. "
    "As consultas operacionais exigem a edição Nexyra + Atlas. "
    "Ações supervisionadas exigem uma 'Nexyra prévia ...' explícita e confirmação."
)

ACTION_CONFIRMATION_TTL_SECONDS = 120.0

ACTION_HELP = (
    "Para alterar algo, use uma prévia explícita. Exemplos: "
    'Nexyra prévia lead.update LEAD-ID {"status":"contatado"}; '
    "Nexyra prévia atribuir LEAD-ID USER-ID; "
    "Nexyra prévia priorizar LEAD-ID urgente; "
    "Nexyra prévia retorno LEAD-ID 2026-09-20T14:00:00-04:00; "
    "Nexyra prévia distribuir 25. "
    "O Atlas só executa depois de mostrar a prévia e você responder 'sim'."
)


@dataclass(frozen=True, slots=True)
class NexyraPendingAction:
    preview: NexyraActionPreview
    client: NexyraClient = field(repr=False)
    created_at: float = field(default_factory=time.monotonic, repr=False)

    def is_expired(self, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return current - self.created_at >= ACTION_CONFIRMATION_TTL_SECONDS


def _action_prefix(text: str) -> str | None:
    """Remove somente o prefixo; o JSON do comando deve permanecer intacto."""
    stripped = text.strip()
    if stripped.lower() == "nexyra":
        return ""
    if stripped[:7].lower() == "nexyra ":
        return stripped[7:].strip()
    return None


def _parse_payload_and_reason(raw: str) -> tuple[dict[str, object], str | None]:
    text = raw.strip()
    if not text:
        return {}, None
    decoder = json.JSONDecoder()
    try:
        payload, end = decoder.raw_decode(text)
    except JSONDecodeError as exc:
        raise NexyraError(
            "invalid_command",
            'A prévia precisa terminar com um objeto JSON válido. Exemplo: {"status":"contatado"}.',
        ) from exc
    if not isinstance(payload, dict):
        raise NexyraError(
            "invalid_command", "O payload da ação precisa ser um objeto JSON."
        )
    trailing = text[end:].strip()
    if not trailing:
        return payload, None
    if not trailing.lower().startswith("; motivo:"):
        raise NexyraError(
            "invalid_command",
            "Depois do JSON use apenas '; motivo: texto opcional'.",
        )
    reason = trailing[len("; motivo:") :].strip()
    if not reason:
        raise NexyraError("invalid_command", "Informe o texto depois de '; motivo:'.")
    return payload, reason


def _parse_operational_alias(body: str) -> NexyraActionRequest | None:
    parts = body.split()
    if not parts or normalize(parts[0]) not in {"previa", "preview", "simular"}:
        return None
    if len(parts) < 2:
        return None

    operation = normalize(parts[1])

    if operation in {"atribuir", "assign"}:
        if len(parts) != 4:
            raise NexyraError(
                "invalid_command",
                "Use: Nexyra prévia atribuir LEAD-ID USER-ID.",
            )
        return NexyraActionRequest(
            "lead.assign",
            parts[2],
            {"user_public_id": parts[3]},
        )

    if operation in {"priorizar", "prioridade"}:
        if len(parts) != 4:
            raise NexyraError(
                "invalid_command",
                "Use: Nexyra prévia priorizar LEAD-ID baixa|media|alta|urgente.",
            )
        return NexyraActionRequest(
            "lead.prioritize",
            parts[2],
            {"priority": normalize(parts[3])},
        )

    if operation in {"retorno", "followup", "follow-up"}:
        if len(parts) != 4:
            raise NexyraError(
                "invalid_command",
                "Use: Nexyra prévia retorno LEAD-ID DATA-ISO.",
            )
        return NexyraActionRequest(
            "lead.followup",
            parts[2],
            {"due_at": parts[3]},
        )

    if operation in {"distribuir", "distribuicao"}:
        raw_limit = parts[-1] if len(parts) >= 3 else "25"
        if len(parts) == 3 and normalize(parts[2]) == "fila":
            raw_limit = "25"
        if len(parts) == 4 and normalize(parts[2]) != "fila":
            raise NexyraError(
                "invalid_command",
                "Use: Nexyra prévia distribuir 25 ou Nexyra prévia distribuir fila 25.",
            )
        try:
            limit = int(raw_limit)
        except ValueError:
            raise NexyraError(
                "invalid_command",
                "O limite da distribuição precisa ser um número inteiro.",
            ) from None
        return NexyraActionRequest(
            "distribution.run",
            None,
            {"limit": limit},
        )

    return None


def parse_action_request(text: str) -> NexyraActionRequest | None:
    """Reconhece somente o formato explícito de prévia de escrita."""
    body = _action_prefix(text)
    if body is None:
        return None
    alias = _parse_operational_alias(body)
    if alias is not None:
        return alias
    parts = body.split(None, 2)
    if not parts or normalize(parts[0]) not in {"previa", "preview", "simular"}:
        return None
    if len(parts) < 2:
        raise NexyraError("invalid_command", ACTION_HELP)
    action = parts[1].strip().lower()
    if action not in {
        "lead.update",
        "opportunity.move",
        "activity.create",
        "activity.complete",
        "lead.assign",
        "lead.prioritize",
        "lead.followup",
        "distribution.run",
    }:
        raise NexyraError(
            "invalid_command",
            "Ação inválida. Use lead.update, opportunity.move, activity.create, "
            "activity.complete, lead.assign, lead.prioritize, lead.followup "
            "ou distribution.run.",
        )
    remainder = parts[2] if len(parts) == 3 else ""
    target: str | None = None
    if action not in {"activity.create", "distribution.run"}:
        target_parts = remainder.split(None, 1)
        if not target_parts:
            raise NexyraError(
                "invalid_command", f"Informe o ID alvo de {action} e o payload JSON."
            )
        target = target_parts[0]
        remainder = target_parts[1] if len(target_parts) == 2 else ""
    payload, reason = _parse_payload_and_reason(remainder)
    if action == "activity.complete" and payload:
        raise NexyraError(
            "invalid_command",
            "activity.complete não aceita payload; use {} se necessário.",
        )
    return NexyraActionRequest(action, target, payload, reason)


def prepare_action(
    text: str,
    client: NexyraClient | None = None,
) -> NexyraPendingAction | None:
    request = parse_action_request(text)
    if request is None:
        return None
    active_client = client or NexyraClient(NexyraConfig.from_env())
    return NexyraPendingAction(active_client.preview_action(request), active_client)


def _json_for_user(value: object) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return "{payload não exibível}"


def format_action_preview(pending: NexyraPendingAction) -> str:
    preview = pending.preview
    target = preview.target_public_id or "(definido no payload)"
    return "\n".join(
        [
            "Prévia Nexyra — nada foi alterado.",
            f"Ação: {preview.action}",
            f"Alvo: {target}",
            f"Resumo: {_text(preview.summary)}",
            f"Payload normalizado: {_json_for_user(preview.normalized_payload)}",
            "Vou revalidar esta mesma ação no CRM imediatamente antes da escrita.",
            "A confirmação expira em 2 minutos.",
            "Responda 'sim' para executar ou 'não' para cancelar.",
        ]
    )


def execute_pending_action(pending: NexyraPendingAction) -> str:
    if pending.is_expired():
        return (
            "A prévia Nexyra expirou após 2 minutos. Nada foi alterado. "
            "Solicite uma nova prévia antes de executar."
        )
    try:
        data = pending.client.execute_action(pending.preview)
    except NexyraError as exc:
        return f"A ação Nexyra não foi executada. {exc}"
    return "\n".join(
        [
            "Ação Nexyra executada com sucesso.",
            f"Ação: {data['action']} | alvo: {data.get('target_public_id') or '(payload)'}.",
            f"Resultado: {_json_for_user(data['result'])}",
            "O CRM confirmou a execução e registrou a auditoria.",
        ]
    )


def parse_command(text: str) -> str | None:
    text = clean_politeness(text)
    if text == "nexyra" or text.startswith("nexyra "):
        command = text.removeprefix("nexyra").strip()
        if command in {"executar", "confirmar", "cancelar"}:
            return "action_help"
        return _COMMANDS.get(command, "help")
    for command, action in _COMMANDS.items():
        if text in {
            f"{command} do nexyra",
            f"{command} no nexyra",
            f"mostre {command} do nexyra",
        }:
            return action

    natural = {
        "quais leads precisam de atencao no nexyra": "queue",
        "quais leads precisam de atencao hoje no nexyra": "queue",
        "quem esta com sla estourada no nexyra": "sla",
        "quais leads estao com sla estourada no nexyra": "sla",
        "quais oportunidades estao em risco no nexyra": "recommendations",
        "quais vendedores estao sobrecarregados no nexyra": "team",
        "resuma a operacao comercial do nexyra": "operations",
        "resumo da operacao comercial do nexyra": "operations",
        "quais leads eu preciso atender agora": "queue",
        "quais leads precisam de atencao agora": "queue",
        "quem esta com sla estourada": "sla",
        "quais leads estao com sla estourada": "sla",
        "quais vendedores estao sobrecarregados": "team",
        "quais oportunidades estao em risco": "recommendations",
        "resuma a operacao comercial de hoje": "operations",
    }
    return natural.get(text)


def _text(value: object) -> str:
    return " ".join(str(value).split())[:240]


def _number(value: object) -> str:
    return (
        f"{Decimal(str(value)):,.2f}".replace(",", "_")
        .replace(".", ",")
        .replace("_", ".")
    )


def _top(items: list[dict], limit: int = 8) -> list[dict]:
    return items[:limit]


def _format_operations(action: str, data: dict) -> str:
    distribution = data["distribution"]
    sla = data["sla"]
    recommendations = data["recommendations"]
    dashboard = data["dashboard"]
    lines = ["Nexyra + Atlas — inteligência operacional"]

    if action == "queue":
        metrics = sla["metrics"]
        lines += [
            f"Leads exigindo atenção: {metrics['total_attention']} | SLA estourada: {metrics['sla_breached']} | alertas: {metrics['sla_warning']}.",
            f"Sem primeiro contato: {metrics['awaiting_first_contact']} | follow-ups vencidos: {metrics['overdue_followups']} | sem responsável: {metrics['unassigned']}.",
        ]
        items = _top(sla["items"], 10)
        if not items:
            lines.append("Nenhum lead retornado na fila de atenção.")
        for item in items:
            owner = item.get("owner_name") or "sem responsável"
            reason = "; ".join(map(_text, item.get("reasons", [])[:2])) or "atenção operacional"
            lines.append(
                f"• {_text(item['lead_name'])} | {_text(item['sla_state'])} | score {item['score']} | {owner} | {reason} | ID {_text(item['lead_public_id'])}"
            )

    elif action == "sla":
        metrics = sla["metrics"]
        lines += [
            f"SLA estourada: {metrics['sla_breached']} | em alerta: {metrics['sla_warning']} | follow-ups vencidos: {metrics['overdue_followups']}.",
        ]
        breached = [item for item in sla["items"] if item["sla_state"] == "breached"]
        if not breached:
            lines.append("Nenhum lead com SLA estourada foi retornado.")
        for item in _top(breached, 10):
            lines.append(
                f"• {_text(item['lead_name'])} | {_text(item.get('owner_name') or 'sem responsável')} | {_text('; '.join(item.get('reasons', [])[:2]))} | ID {_text(item['lead_public_id'])}"
            )

    elif action == "recommendations":
        metrics = recommendations["metrics"]
        lines += [
            f"Recomendações: críticas {metrics['critical']} | altas {metrics['high']} | aguardando resposta {metrics['awaiting_reply']} | oportunidades em risco {metrics['opportunities_at_risk']}.",
        ]
        items = [
            item
            for item in recommendations["items"]
            if item["urgency"] in {"critical", "high"}
        ] or recommendations["items"]
        if not items:
            lines.append("Nenhuma recomendação comercial foi retornada.")
        for item in _top(items, 10):
            reason = "; ".join(map(_text, item.get("reasons", [])[:2]))
            lines.append(
                f"• {_text(item['lead_name'])}: {_text(item['action_title'])} | {_text(item['urgency'])} | score {item['score']} | canal {_text(item['suggested_channel'])} | {reason} | ID {_text(item['lead_public_id'])}"
            )

    elif action == "team":
        lines += [
            f"Distribuição automática: {'ativa' if distribution['enabled'] else 'desativada'} | estratégia: {_text(distribution['strategy'])}.",
            f"Leads ativos: {distribution['total_active_leads']} | sem responsável: {distribution['unassigned_active_leads']}.",
        ]
        members = sorted(
            distribution["members"],
            key=lambda item: (-item["assigned_active_leads"], item["name"]),
        )
        for item in members:
            status = "elegível" if item["eligible"] else "fora da distribuição"
            lines.append(
                f"• {_text(item['name'])} ({_text(item['role'])}): {item['assigned_active_leads']} leads ativos | {status}."
            )

    elif action == "dashboard":
        rec = dashboard["recommendations"]
        dash_sla = dashboard["sla"]
        lines += [
            f"Período: {dashboard.get('period_days', 30)} dias | leads ativos: {dashboard['active_leads']} | novos: {dashboard['leads_created']} | sem responsável: {dashboard['unassigned_leads']}.",
            f"Oportunidades abertas: {dashboard['open_opportunities']} | conversão: {_number(dashboard.get('conversion_rate', 0))}% | valor ganho: {_number(dashboard.get('won_value', 0))}.",
            f"SLA estourada: {dash_sla.get('breached', 0)} | atenção: {dash_sla.get('total_attention', 0)} | recomendações críticas: {rec.get('critical', 0)}.",
        ]
        for item in _top(dashboard.get("bottlenecks", []), 6):
            lines.append(
                f"• Gargalo: {_text(item.get('title', item.get('code', '')))} — {item.get('count', 0)} ({_text(item.get('severity', ''))})."
            )

    else:  # operations
        metrics = sla["metrics"]
        rec = recommendations["metrics"]
        lines += [
            f"Leads ativos: {dashboard['active_leads']} | sem responsável: {distribution['unassigned_active_leads']} | SLA estourada: {metrics['sla_breached']}.",
            f"Recomendações críticas: {rec['critical']} | altas: {rec['high']} | oportunidades em risco: {rec['opportunities_at_risk']}.",
            f"Oportunidades abertas: {dashboard['open_opportunities']} | conversão: {_number(dashboard.get('conversion_rate', 0))}% | atividades vencidas: {dashboard['overdue_activities']}.",
            f"Distribuição: {'ativa' if distribution['enabled'] else 'desativada'} ({_text(distribution['strategy'])}).",
        ]
        if dashboard.get("bottlenecks"):
            lines.append(
                "Principais gargalos: "
                + "; ".join(
                    f"{_text(item.get('title', item.get('code', '')))} ({item.get('count', 0)})"
                    for item in _top(dashboard["bottlenecks"], 4)
                )
                + "."
            )

    lines.append("Fonte: API Nexyra + Atlas, consultada agora.")
    return "\n".join(lines)


def format_response(action: str, data: dict) -> str:
    if action in {"queue", "sla", "recommendations", "dashboard", "team", "operations"}:
        return _format_operations(action, data)

    context = data["context"]
    workspace, actor = context["workspace"], context["actor"]
    counts, metrics = context["counts"], context["opportunity_metrics"]
    lines = [f"Nexyra — {_text(workspace['name'])}"]
    if action == "diagnose":
        lines += [
            "Conexão e acesso de consulta validados.",
            f"CRM {_text(data['health']['crm_version'])} | contrato 1.0.",
            f"Usuário: {_text(actor['name'])} ({_text(actor['role'])}).",
            "Permissão de consulta: atlas.use.",
            "Capacidades: "
            + ", ".join(map(_text, data["capabilities"]["capabilities"])),
            "Alterações pelo Atlas: supervisionadas por prévia, revalidação e confirmação.",
        ]
    elif action in {"summary", "metrics"}:
        lines += [
            f"Leads: {counts['leads']} | ativos: {counts['active_leads']}.",
            f"Oportunidades: {metrics['total_opportunities']} | abertas: {metrics['open_opportunities']} | ganhas: {metrics['won_opportunities']} | perdidas: {metrics['lost_opportunities']}.",
            f"Conversão entre oportunidades encerradas: {_number(metrics['conversion_rate'])}%.",
            f"Valor do pipeline: {_number(metrics['total_pipeline_value'])} | valor ganho: {_number(metrics['won_value'])}.",
            "Valores na unidade monetária usada pelo CRM; o contrato não informa a moeda.",
            f"Pendências da empresa: {counts['pending_followups']}.",
        ]
    elif action == "pending":
        items = context["pending_followups"]
        lines.append(
            f"Pendências da empresa: {counts['pending_followups']}. Exibindo {len(items)}; a API retorna no máximo 25 por consulta."
        )
        if not items:
            lines.append("Nenhuma pendência retornada nesta consulta.")
        for item in items:
            state = "atrasada" if item["overdue"] else "pendente"
            lines.append(
                f"• {_text(item['title'])} — {state} | prazo: {_text(item['due_at'] or 'sem prazo')} | ID: {_text(item['public_id'])}"
            )
        lines.append(
            "Prazos exibidos com o fuso informado pelo CRM. A lista é da empresa, não apenas do usuário."
        )
    elif action == "sources":
        for item in context["lead_sources"]:
            lines.append(
                f"• {_text(item['source'])} / {_text(item['channel'])}: {item['lead_count']} leads ativos."
            )
        if not context["lead_sources"]:
            lines.append("Nenhuma origem de lead ativo retornada.")
    lines.append("Fonte: API Nexyra, consultada agora; sem filtro de período.")
    return "\n".join(lines)


def handle_command(text: str, driver: NexyraApiDriver | None = None) -> str | None:
    action = parse_command(text)
    if action is None:
        return None
    if action == "action_help":
        return "Não há ação Nexyra pendente. " + ACTION_HELP
    if action == "help":
        return HELP
    result = (driver or NexyraApiDriver()).execute(action)
    if not result.ok:
        return f"Não consegui consultar o Nexyra. {result.error}"
    return format_response(action, result.data)
