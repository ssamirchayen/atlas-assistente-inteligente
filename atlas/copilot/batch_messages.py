from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from atlas.integrations.base import IntegrationResult

from .models import (
    CopilotActionResult,
    CopilotRequest,
    CopilotResponse,
)

DEFAULT_BATCH_LIMIT = 10
MIN_BATCH_LIMIT = 1
MAX_BATCH_LIMIT = 50
MAX_EXECUTION_LIMIT = 25
MAX_FETCH_LIMIT = 120
VALID_LEAD_STATUSES = {"novo", "em_atendimento", "follow_up", "convertido", "perdido"}
PROTECTED_DEFAULT_STATUSES = {"convertido", "perdido"}


class BatchMessageExecutor(Protocol):
    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult: ...


@dataclass(frozen=True, slots=True)
class BatchMessageFilters:
    requested_limit: int
    fetch_limit: int
    course_id: int | None = None
    course_name: str = ""
    status: str = ""
    priority: str = ""

    def to_api_kwargs(self) -> dict[str, Any]:
        return {
            "course_id": self.course_id,
            "status": self.status,
            "priority": self.priority,
            "limit": self.fetch_limit,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_limit": self.requested_limit,
            "fetch_limit": self.fetch_limit,
            "course_id": self.course_id,
            "course_name": self.course_name,
            "status": self.status,
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True)
class BatchMessageItem:
    code: str
    name: str
    course_name: str
    status: str
    priority: str
    source: str
    message: str
    recommended_channel: str
    suggested_outcome: str
    needs_followup: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "course_name": self.course_name,
            "status": self.status,
            "priority": self.priority,
            "source": self.source,
            "message": self.message,
            "recommended_channel": self.recommended_channel,
            "suggested_outcome": self.suggested_outcome,
            "needs_followup": self.needs_followup,
        }


@dataclass(frozen=True, slots=True)
class BatchExecutionSummary:
    selected_count: int
    interaction_success: int = 0
    interaction_failed: int = 0
    followup_success: int = 0
    followup_failed: int = 0
    status_success: int = 0
    status_failed: int = 0
    status_skipped: int = 0
    target_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_count": self.selected_count,
            "interaction_success": self.interaction_success,
            "interaction_failed": self.interaction_failed,
            "followup_success": self.followup_success,
            "followup_failed": self.followup_failed,
            "status_success": self.status_success,
            "status_failed": self.status_failed,
            "status_skipped": self.status_skipped,
            "target_status": self.target_status,
        }


@dataclass(frozen=True, slots=True)
class BatchStatusUpdatePlan:
    enabled: bool
    target_status: str = ""
    explicit: bool = False
    reason: str = ""
    updateable_count: int = 0
    skipped_count: int = 0
    skipped_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "target_status": self.target_status,
            "explicit": self.explicit,
            "reason": self.reason,
            "updateable_count": self.updateable_count,
            "skipped_count": self.skipped_count,
            "skipped_codes": list(self.skipped_codes),
        }


def looks_like_batch_message_command(message: str) -> bool:
    text = _normalize(message)
    if "lead" not in text and "atendimento" not in text:
        return False

    batch_marker = any(
        marker in text
        for marker in (
            "varios",
            "todos",
            "lote",
            "massa",
            "carteira",
            "multiplos",
            "multiplo",
        )
    ) or bool(re.search(r"\b\d{1,3}\s+leads?\b", text))

    work_marker = any(
        marker in text
        for marker in (
            "mensagem",
            "mensagens",
            "atendimento",
            "atendimentos",
            "registre",
            "registrar",
            "enviar",
            "envie",
            "mandar",
            "mande",
            "preparar",
            "prepare",
            "rascunho",
            "rascunhos",
        )
    )
    return batch_marker and work_marker


def run_batch_message_workflow(
    request: CopilotRequest,
    manager: BatchMessageExecutor,
    payload: dict[str, Any] | None = None,
) -> CopilotResponse:
    safe_payload = payload or {}
    courses_result = manager.execute("business_lab", "list_courses")
    filters = _build_filters(
        message=request.message,
        courses=_safe_list(courses_result.data) if courses_result.ok else [],
    )
    leads_result = manager.execute(
        "business_lab",
        "list_leads",
        **filters.to_api_kwargs(),
    )
    actions = [_action_result(courses_result), _action_result(leads_result)]

    if not leads_result.ok:
        return CopilotResponse(
            ok=False,
            intent="batch_messages",
            context=request.context,
            answer=leads_result.error or "Não consegui buscar leads para o lote.",
            actions=tuple(actions),
            error=leads_result.error or "Falha ao buscar leads.",
        )

    leads = _safe_list(leads_result.data)
    if not leads:
        return CopilotResponse(
            ok=True,
            intent="batch_messages",
            context=request.context,
            answer=(
                "Não encontrei leads para atendimento em lote com esses filtros. "
                "Tente remover curso, status ou prioridade."
            ),
            actions=tuple(actions),
            data={
                "filters": filters.to_dict(),
                "selected_count": 0,
                "messages": [],
                "execution_plan": _preview_execution_plan(),
            },
            requires_human_review=True,
        )

    custom_message = _extract_custom_message(request.message, safe_payload)
    selected = _select_message_items(
        leads=leads,
        limit=filters.requested_limit,
        custom_message=custom_message,
    )
    create_followups = _should_create_followups(request.message, safe_payload)
    status_plan = _build_status_update_plan(
        message=request.message,
        payload=safe_payload,
        create_followups=create_followups,
        selected=selected,
    )
    confirmed = bool(safe_payload.get("confirmed") is True)

    if request.dry_run or not confirmed:
        return _preview_response(
            request=request,
            filters=filters,
            total_candidates=len(leads),
            selected=selected,
            create_followups=create_followups,
            status_plan=status_plan,
            actions=tuple(actions),
        )

    if len(selected) > MAX_EXECUTION_LIMIT:
        return CopilotResponse(
            ok=False,
            intent="batch_messages",
            context=request.context,
            answer=(
                "Bloqueei a execução: o lote selecionado passou do limite seguro "
                f"de {MAX_EXECUTION_LIMIT} leads por vez. Reduza o filtro."
            ),
            actions=tuple(actions),
            data={
                "filters": filters.to_dict(),
                "selected_count": len(selected),
                "limit": MAX_EXECUTION_LIMIT,
                "mode": "blocked_by_safety_limit",
            },
            error="Limite seguro de execução em lote excedido.",
            requires_human_review=True,
        )

    execution = _execute_batch(
        selected=selected,
        manager=manager,
        create_followups=create_followups,
        status_plan=status_plan,
        message=request.message,
    )
    actions.extend(execution["actions"])
    summary = execution["summary"]
    summary_dict = summary.to_dict()
    answer = _format_execution_answer(
        selected=selected,
        summary=summary,
        create_followups=create_followups,
    )

    return CopilotResponse(
        ok=(
            summary.interaction_failed == 0
            and summary.followup_failed == 0
            and summary.status_failed == 0
        ),
        intent="batch_messages",
        context=request.context,
        answer=answer,
        actions=tuple(actions),
        data={
            "filters": filters.to_dict(),
            "selected_count": len(selected),
            "messages": [item.to_dict() for item in selected],
            "execution": summary_dict,
            "status_update_plan": status_plan.to_dict(),
            "mode": "confirmed_business_lab_records",
            "external_delivery": "disabled",
            "safety_notes": _safety_notes(),
        },
        requires_human_review=False,
    )


def _preview_response(
    *,
    request: CopilotRequest,
    filters: BatchMessageFilters,
    total_candidates: int,
    selected: list[BatchMessageItem],
    create_followups: bool,
    status_plan: BatchStatusUpdatePlan,
    actions: tuple[CopilotActionResult, ...],
) -> CopilotResponse:
    return CopilotResponse(
        ok=True,
        intent="batch_messages",
        context=request.context,
        answer=_format_preview_answer(
            items=selected,
            filters=filters,
            total_candidates=total_candidates,
            create_followups=create_followups,
            status_plan=status_plan,
        ),
        actions=actions,
        data={
            "filters": filters.to_dict(),
            "total_candidates": total_candidates,
            "selected_count": len(selected),
            "messages": [item.to_dict() for item in selected],
            "execution_plan": _preview_execution_plan(
                create_followups=create_followups,
                status_plan=status_plan,
            ),
            "status_update_plan": status_plan.to_dict(),
            "confirmation_required": True,
            "external_delivery": "disabled",
            "safety_notes": _safety_notes(),
        },
        requires_human_review=True,
    )


def _execute_batch(
    *,
    selected: list[BatchMessageItem],
    manager: BatchMessageExecutor,
    create_followups: bool,
    status_plan: BatchStatusUpdatePlan,
    message: str,
) -> dict[str, Any]:
    action_results: list[CopilotActionResult] = []
    interaction_success = 0
    interaction_failed = 0
    followup_success = 0
    followup_failed = 0
    status_success = 0
    status_failed = 0
    status_skipped = 0
    due_at = _extract_due_at(message)

    for item in selected:
        interaction = manager.execute(
            "business_lab",
            "create_interaction",
            code=item.code,
            channel=item.recommended_channel,
            kind="mensagem",
            direction="saida",
            outcome=item.suggested_outcome,
            content=item.message,
        )
        action_results.append(_action_result(interaction))
        if interaction.ok:
            interaction_success += 1
        else:
            interaction_failed += 1

        if create_followups:
            followup = manager.execute(
                "business_lab",
                "create_followup",
                code=item.code,
                title="Retorno criado em lote pelo Atlas",
                notes=(
                    "Retorno criado pelo Atlas após atendimento/mensagem em lote. "
                    f"Comando original: {message}"
                ),
                priority=_safe_priority(item.priority),
                due_at=due_at,
            )
            action_results.append(_action_result(followup))
            if followup.ok:
                followup_success += 1
            else:
                followup_failed += 1

        if not status_plan.enabled:
            continue

        if not interaction.ok or _should_skip_status_update(
            item,
            status_plan.target_status,
            status_plan.explicit,
        ):
            status_skipped += 1
            continue

        status_update = manager.execute(
            "business_lab",
            "update_lead_status",
            code=item.code,
            status=status_plan.target_status,
        )
        action_results.append(_action_result(status_update))
        if status_update.ok:
            status_success += 1
        else:
            status_failed += 1

    summary = BatchExecutionSummary(
        selected_count=len(selected),
        interaction_success=interaction_success,
        interaction_failed=interaction_failed,
        followup_success=followup_success,
        followup_failed=followup_failed,
        status_success=status_success,
        status_failed=status_failed,
        status_skipped=status_skipped,
        target_status=status_plan.target_status,
    )
    return {"actions": action_results, "summary": summary}


def _build_filters(
    *,
    message: str,
    courses: list[Any],
) -> BatchMessageFilters:
    text = _normalize(message)
    requested_limit = _extract_limit(text)
    course_id, course_name = _extract_course(text, courses)
    status = _extract_status(text)
    priority = _extract_priority(text)
    fetch_limit = min(MAX_FETCH_LIMIT, max(30, requested_limit * 4))
    return BatchMessageFilters(
        requested_limit=requested_limit,
        fetch_limit=fetch_limit,
        course_id=course_id,
        course_name=course_name,
        status=status,
        priority=priority,
    )


def _extract_limit(text: str) -> int:
    match = re.search(r"\b(\d{1,3})\s+leads?\b", text)
    if match is None:
        match = re.search(r"\b(\d{1,3})\b", text)
    if match is None:
        return DEFAULT_BATCH_LIMIT
    return max(MIN_BATCH_LIMIT, min(int(match.group(1)), MAX_BATCH_LIMIT))


def _extract_course(text: str, courses: list[Any]) -> tuple[int | None, str]:
    for course in courses:
        if not isinstance(course, dict):
            continue
        name = str(course.get("name") or "")
        normalized = _normalize(name)
        if normalized and normalized in text:
            return int(course.get("id") or 0), name
    return None, ""


def _extract_status(text: str) -> str:
    if "em atendimento" in text or "em_atendimento" in text:
        return "em_atendimento"
    if "follow up" in text or "follow-up" in text or "follow_up" in text:
        return "follow_up"
    if "convertido" in text or "convertidos" in text:
        return "convertido"
    if "perdido" in text or "perdidos" in text:
        return "perdido"
    if "novo" in text or "novos" in text:
        return "novo"
    return ""


def _extract_priority(text: str) -> str:
    if "prioridade alta" in text or "alta prioridade" in text:
        return "alta"
    if "prioridade media" in text or "prioridade média" in text:
        return "media"
    if "prioridade baixa" in text or "baixa prioridade" in text:
        return "baixa"
    return ""


def _select_message_items(
    *,
    leads: list[Any],
    limit: int,
    custom_message: str,
) -> list[BatchMessageItem]:
    items = [
        _build_item(lead, custom_message=custom_message)
        for lead in leads
        if isinstance(lead, dict)
    ]
    items.sort(key=_ranking_key)
    return items[:limit]


def _build_item(
    lead: dict[str, Any],
    *,
    custom_message: str,
) -> BatchMessageItem:
    code = str(lead.get("synthetic_code") or "")
    name = str(lead.get("name") or "lead")
    course_name = str(lead.get("course_name") or "curso de interesse")
    status = str(lead.get("status") or "")
    priority = str(lead.get("priority") or "")
    source = str(lead.get("source") or "")
    message = custom_message or _personalized_message(
        name=name,
        course_name=course_name,
        status=status,
        priority=priority,
    )
    return BatchMessageItem(
        code=code,
        name=name,
        course_name=course_name,
        status=status or "não informado",
        priority=priority or "não informada",
        source=source or "não informada",
        message=message,
        recommended_channel=_recommended_channel(source),
        suggested_outcome=_suggested_outcome(status),
        needs_followup=status in {"novo", "em_atendimento", "follow_up"},
    )


def _personalized_message(
    *,
    name: str,
    course_name: str,
    status: str,
    priority: str,
) -> str:
    first_name = name.split()[0] if name else "tudo bem"
    if status == "follow_up":
        return (
            f"Olá, {first_name}! Passando para retomar seu interesse em "
            f"{course_name}. Posso te ajudar a avançar com a matrícula?"
        )
    if status == "em_atendimento":
        return (
            f"Olá, {first_name}! Vi que você está em atendimento sobre "
            f"{course_name}. Quer que eu te envie as condições de matrícula?"
        )
    if priority == "alta":
        return (
            f"Olá, {first_name}! Temos uma oportunidade importante para "
            f"{course_name}. Posso te passar os próximos passos da matrícula?"
        )
    return (
        f"Olá, {first_name}! Vi seu interesse em {course_name}. "
        "Posso te ajudar com informações de matrícula e turma?"
    )


def _ranking_key(item: BatchMessageItem) -> tuple[int, int, int]:
    priority_rank = {"alta": 0, "media": 1, "baixa": 2}.get(item.priority, 3)
    status_rank = {
        "follow_up": 0,
        "em_atendimento": 1,
        "novo": 2,
        "convertido": 3,
        "perdido": 4,
    }.get(item.status, 5)
    followup_rank = 0 if item.needs_followup else 1
    return priority_rank, status_rank, followup_rank


def _recommended_channel(source: str) -> str:
    if source == "WhatsApp":
        return "WhatsApp"
    if source == "Site":
        return "E-mail"
    return "WhatsApp"


def _suggested_outcome(status: str) -> str:
    if status == "follow_up":
        return "retorno_agendado"
    if status in {"novo", "em_atendimento"}:
        return "interessado"
    return "sem_resposta"


def _safe_priority(priority: str) -> str:
    if priority in {"baixa", "media", "alta"}:
        return priority
    return "media"


def _build_status_update_plan(
    *,
    message: str,
    payload: dict[str, Any],
    create_followups: bool,
    selected: list[BatchMessageItem],
) -> BatchStatusUpdatePlan:
    target_status, explicit, reason = _extract_target_status(
        message=message,
        payload=payload,
        create_followups=create_followups,
    )
    if not target_status:
        return BatchStatusUpdatePlan(enabled=False)

    skipped_codes: list[str] = []
    updateable_count = 0
    for item in selected:
        if _should_skip_status_update(item, target_status, explicit):
            skipped_codes.append(item.code)
        else:
            updateable_count += 1

    return BatchStatusUpdatePlan(
        enabled=True,
        target_status=target_status,
        explicit=explicit,
        reason=reason,
        updateable_count=updateable_count,
        skipped_count=len(skipped_codes),
        skipped_codes=tuple(skipped_codes),
    )


def _extract_target_status(
    *,
    message: str,
    payload: dict[str, Any],
    create_followups: bool,
) -> tuple[str, bool, str]:
    for key in ("target_status", "lead_status", "status_to_set"):
        status = _canonical_status(str(payload.get(key) or ""))
        if status:
            return status, True, f"status informado em {key}"

    text = _normalize(message)
    explicit_status_requested = any(
        marker in text
        for marker in (
            "atualize",
            "atualizar",
            "altere",
            "alterar",
            "mude",
            "mudar",
            "mova",
            "mover",
            "coloque",
            "marque",
            "status",
        )
    )
    if explicit_status_requested:
        status = _canonical_status(text)
        if status:
            return status, True, "status solicitado explicitamente no comando"

    if payload.get("update_status") is True:
        if create_followups:
            return "follow_up", True, "update_status=true com retorno em lote"
        return "em_atendimento", True, "update_status=true com atendimento em lote"

    if create_followups:
        return "follow_up", False, "retorno criado em lote"

    if any(
        marker in text
        for marker in (
            "registre atendimento",
            "registrar atendimento",
            "atendimento em lote",
            "atendimentos em lote",
        )
    ):
        return "em_atendimento", False, "atendimento registrado em lote"

    return "", False, ""


def _canonical_status(value: str) -> str:
    text = _normalize(value)
    aliases = {
        "follow_up": (
            "follow_up",
            "follow up",
            "follow-up",
            "retorno",
            "retornos",
            "em retorno",
        ),
        "em_atendimento": (
            "em_atendimento",
            "em atendimento",
            "atendimento",
            "atendendo",
        ),
        "convertido": ("convertido", "convertidos", "matriculado"),
        "perdido": ("perdido", "perdidos", "sem interesse"),
        "novo": ("novo", "novos"),
    }
    for status, options in aliases.items():
        if any(option in text for option in options):
            return status
    return text if text in VALID_LEAD_STATUSES else ""


def _should_skip_status_update(
    item: BatchMessageItem,
    target_status: str,
    explicit: bool,
) -> bool:
    if not item.code or not target_status:
        return True
    if item.status == target_status:
        return True
    if explicit:
        return False
    if item.status in PROTECTED_DEFAULT_STATUSES:
        return True
    if target_status == "em_atendimento" and item.status != "novo":
        return True
    return False


def _should_create_followups(
    message: str,
    payload: dict[str, Any],
) -> bool:
    if payload.get("create_followups") is True:
        return True
    text = _normalize(message)
    return any(
        marker in text
        for marker in (
            "retorno",
            "retornos",
            "agendar",
            "agende",
            "amanha",
            "amanhã",
        )
    )


def _extract_custom_message(
    message: str,
    payload: dict[str, Any],
) -> str:
    raw_content = payload.get("content") or payload.get("message_template") or ""
    content = str(raw_content).strip()
    if content:
        return content

    lowered = message.lower()
    for marker in (
        "mensagem:",
        "dizendo:",
        "dizendo que",
        "informando:",
        "informando que",
        "avisando que",
    ):
        index = lowered.find(marker)
        if index >= 0:
            extracted = message[index + len(marker) :].strip(" :.-")
            if extracted:
                return extracted
    return ""


def _extract_due_at(message: str) -> str:
    text = _normalize(message)
    hour = 15
    minute = 0
    match = re.search(r"(\d{1,2})(?:h|:)(\d{2})?", text)
    if match:
        hour = max(0, min(int(match.group(1)), 23))
        if match.group(2):
            minute = max(0, min(int(match.group(2)), 59))
    due = datetime.now() + timedelta(days=1)
    return due.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    ).isoformat(timespec="minutes")


def _format_preview_answer(
    *,
    items: list[BatchMessageItem],
    filters: BatchMessageFilters,
    total_candidates: int,
    create_followups: bool,
    status_plan: BatchStatusUpdatePlan,
) -> str:
    filter_text = _format_filters(filters)
    lines = [
        "Prévia de atendimentos/mensagens em lote pronta.",
        f"Encontrei {total_candidates} leads com {filter_text}.",
        f"Separei {len(items)} leads para revisão antes de executar.",
        "Amostra das mensagens:",
    ]
    for index, item in enumerate(items[:5], start=1):
        lines.append(f"{index}. {item.code} — {item.name}: {item.message}")
    if create_followups:
        lines.append("Também preparei criação de retornos para amanhã.")
    if status_plan.enabled:
        lines.append(
            "Após confirmação, vou atualizar status para "
            f"{status_plan.target_status}: "
            f"{status_plan.updateable_count} alterações e "
            f"{status_plan.skipped_count} ignorados."
        )
    lines.append(
        "Nenhuma mensagem externa foi enviada. Nenhum atendimento foi registrado "
        "sem confirmação explícita."
    )
    return "\n".join(lines)


def _format_execution_answer(
    *,
    selected: list[BatchMessageItem],
    summary: BatchExecutionSummary,
    create_followups: bool,
) -> str:
    lines = [
        "Execução em lote concluída dentro do Business Lab.",
        (
            f"Atendimentos registrados: {summary.interaction_success}/"
            f"{summary.selected_count}."
        ),
    ]
    if create_followups:
        lines.append(
            f"Retornos criados: {summary.followup_success}/{summary.selected_count}."
        )
    if summary.target_status:
        lines.append(
            f"Status atualizados para {summary.target_status}: "
            f"{summary.status_success}/{summary.selected_count}."
        )
        if summary.status_skipped:
            lines.append(
                f"Status ignorados: {summary.status_skipped} "
                "(já estavam corretos ou foram protegidos pela regra segura)."
            )
    if summary.interaction_failed or summary.followup_failed or summary.status_failed:
        lines.append(
            "Alguns itens falharam. Consulte os detalhes das ações retornadas."
        )
    lines.append(
        "Importante: isso registrou histórico no Business Lab; não enviou WhatsApp "
        "ou e-mail real."
    )
    lines.append("Leads processados: " + ", ".join(item.code for item in selected))
    return "\n".join(lines)


def _format_filters(filters: BatchMessageFilters) -> str:
    parts = []
    if filters.course_name:
        parts.append(f"curso {filters.course_name}")
    if filters.status:
        parts.append(f"status {filters.status}")
    if filters.priority:
        parts.append(f"prioridade {filters.priority}")
    return ", ".join(parts) if parts else "filtros amplos"


def _preview_execution_plan(
    create_followups: bool = False,
    status_plan: BatchStatusUpdatePlan | None = None,
) -> dict[str, Any]:
    planned = ["registrar atendimento/mensagem no histórico do Business Lab"]
    if create_followups:
        planned.append("criar retornos para amanhã")
    if status_plan and status_plan.enabled:
        planned.append(f"atualizar status dos leads para {status_plan.target_status}")
    return {
        "mode": "preview_only",
        "requires_confirmation": True,
        "planned_actions": planned,
        "executed_actions": [],
        "max_execution_limit": MAX_EXECUTION_LIMIT,
    }


def _safety_notes() -> list[str]:
    return [
        "mensagens externas reais ficam desativadas nesta etapa",
        "o Atlas registra rascunho/histórico no Business Lab, não envia WhatsApp",
        "execução em lote exige confirmed=true",
        "respeitar LGPD, opt-out, consentimento e limites anti-spam",
    ]


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _action_result(result: IntegrationResult) -> CopilotActionResult:
    return CopilotActionResult(
        action=result.action,
        ok=result.ok,
        driver=result.driver.value if result.driver else None,
        error=result.error,
        data=result.data,
    )


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode(
        "ascii",
        "ignore",
    ).decode("ascii")
    return " ".join(text.lower().split())
