from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from atlas.integrations.base import IntegrationResult

from .models import (
    CopilotActionResult,
    CopilotPageContext,
    CopilotRequest,
    CopilotResponse,
)

DEFAULT_TRIAGE_LIMIT = 10
MIN_TRIAGE_LIMIT = 1
MAX_TRIAGE_LIMIT = 50
MAX_FETCH_LIMIT = 100


class BatchIntegrationExecutor(Protocol):
    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult: ...


@dataclass(frozen=True, slots=True)
class LeadTriageItem:
    code: str
    name: str
    course_name: str
    status: str
    priority: str
    source: str
    score: int
    reason: str
    recommended_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "course_name": self.course_name,
            "status": self.status,
            "priority": self.priority,
            "source": self.source,
            "score": self.score,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True, slots=True)
class LeadTriageFilters:
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


def looks_like_batch_lead_triage(message: str) -> bool:
    text = _normalize(message)
    if "lead" not in text:
        return False

    has_batch_marker = any(
        marker in text
        for marker in (
            "varios",
            "todos",
            "lote",
            "massa",
            "carteira",
            "pendentes",
            "prioritarios",
        )
    ) or bool(re.search(r"\b\d{1,3}\s+leads?\b", text))

    has_triage_marker = any(
        marker in text
        for marker in (
            "analise",
            "analisar",
            "triagem",
            "priorize",
            "priorizar",
            "separe",
            "ranking",
            "rankear",
            "plano",
            "proxima acao",
            "proxima ação",
        )
    )
    return has_batch_marker and has_triage_marker


def run_batch_lead_triage(
    request: CopilotRequest,
    manager: BatchIntegrationExecutor,
) -> CopilotResponse:
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
    actions = (_action_result(courses_result), _action_result(leads_result))

    if not leads_result.ok:
        return CopilotResponse(
            ok=False,
            intent="batch_lead_triage",
            context=request.context,
            answer=leads_result.error or "Não consegui buscar os leads.",
            actions=actions,
            error=leads_result.error or "Falha ao buscar leads.",
        )

    leads = _safe_list(leads_result.data)
    if not leads:
        return CopilotResponse(
            ok=True,
            intent="batch_lead_triage",
            context=request.context,
            answer=(
                "Não encontrei leads com esses filtros. "
                "Tente remover curso, status ou prioridade."
            ),
            actions=actions,
            data={
                "filters": filters.to_dict(),
                "total_candidates": 0,
                "selected": [],
                "summary": {},
                "execution_plan": _safe_execution_plan(),
            },
            requires_human_review=True,
        )

    triage_items = sorted(
        (_triage_lead(item) for item in leads if isinstance(item, dict)),
        key=lambda item: item.score,
        reverse=True,
    )[: filters.requested_limit]

    summary = _build_summary(triage_items)
    answer = _format_batch_answer(
        items=triage_items,
        filters=filters,
        total_candidates=len(leads),
        context=request.context,
    )

    return CopilotResponse(
        ok=True,
        intent="batch_lead_triage",
        context=request.context,
        answer=answer,
        actions=actions,
        data={
            "filters": filters.to_dict(),
            "total_candidates": len(leads),
            "selected_count": len(triage_items),
            "selected": [item.to_dict() for item in triage_items],
            "summary": summary,
            "execution_plan": _safe_execution_plan(),
        },
        requires_human_review=True,
    )


def _build_filters(
    *,
    message: str,
    courses: list[Any],
) -> LeadTriageFilters:
    text = _normalize(message)
    requested_limit = _extract_limit(text)
    course_id, course_name = _extract_course(text, courses)
    status = _extract_status(text)
    priority = _extract_priority(text)

    fetch_limit = min(
        MAX_FETCH_LIMIT,
        max(30, requested_limit * 4),
    )
    return LeadTriageFilters(
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
        return DEFAULT_TRIAGE_LIMIT

    value = int(match.group(1))
    return max(MIN_TRIAGE_LIMIT, min(value, MAX_TRIAGE_LIMIT))


def _extract_course(
    text: str,
    courses: list[Any],
) -> tuple[int | None, str]:
    for course in courses:
        if not isinstance(course, dict):
            continue
        raw_name = str(course.get("name") or "")
        normalized_name = _normalize(raw_name)
        if normalized_name and normalized_name in text:
            raw_id = course.get("id")
            return int(raw_id), raw_name
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


def _triage_lead(lead: dict[str, Any]) -> LeadTriageItem:
    status = str(lead.get("status") or "")
    priority = str(lead.get("priority") or "")
    source = str(lead.get("source") or "")
    score, reasons = _score_lead(
        status=status,
        priority=priority,
        source=source,
    )
    return LeadTriageItem(
        code=str(lead.get("synthetic_code") or ""),
        name=str(lead.get("name") or "sem nome"),
        course_name=str(lead.get("course_name") or "curso não informado"),
        status=status or "não informado",
        priority=priority or "não informada",
        source=source or "não informada",
        score=score,
        reason="; ".join(reasons),
        recommended_action=_recommended_action(status=status, priority=priority),
    )


def _score_lead(
    *,
    status: str,
    priority: str,
    source: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    priority_points = {
        "alta": 45,
        "media": 25,
        "baixa": 10,
    }.get(priority, 0)
    if priority_points:
        score += priority_points
        reasons.append(f"prioridade {priority}")

    status_points = {
        "novo": 25,
        "em_atendimento": 30,
        "follow_up": 35,
        "convertido": -20,
        "perdido": -35,
    }.get(status, 0)
    if status_points:
        score += status_points
        reasons.append(f"status {status}")

    source_points = {
        "WhatsApp": 8,
        "Instagram": 6,
        "Site": 5,
        "Indicação": 7,
    }.get(source, 0)
    if source_points:
        score += source_points
        reasons.append(f"origem {source}")

    if not reasons:
        reasons.append("dados insuficientes para priorização avançada")
    return score, reasons


def _recommended_action(*, status: str, priority: str) -> str:
    if status == "novo":
        return "fazer primeiro contato e registrar atendimento."
    if status == "em_atendimento" and priority == "alta":
        return "priorizar contato agora e agendar retorno curto."
    if status == "em_atendimento":
        return "continuar atendimento e confirmar objeção principal."
    if status == "follow_up":
        return "retomar conversa e tentar avançar para matrícula."
    if status == "convertido":
        return "conferir matrícula e pagamento antes de novo contato."
    if status == "perdido":
        return "não insistir sem novo interesse registrado."
    return "registrar atendimento e definir próximo retorno."


def _build_summary(items: list[LeadTriageItem]) -> dict[str, Any]:
    priorities = Counter(item.priority for item in items)
    statuses = Counter(item.status for item in items)
    courses = Counter(item.course_name for item in items)
    return {
        "by_priority": dict(priorities),
        "by_status": dict(statuses),
        "by_course": dict(courses),
        "top_score": items[0].score if items else 0,
        "average_score": (
            round(sum(item.score for item in items) / len(items), 2)
            if items
            else 0
        ),
    }


def _format_batch_answer(
    *,
    items: list[LeadTriageItem],
    filters: LeadTriageFilters,
    total_candidates: int,
    context: CopilotPageContext,
) -> str:
    filter_parts = []
    if filters.course_name:
        filter_parts.append(f"curso {filters.course_name}")
    if filters.status:
        filter_parts.append(f"status {filters.status}")
    if filters.priority:
        filter_parts.append(f"prioridade {filters.priority}")

    filter_text = ", ".join(filter_parts) if filter_parts else "sem filtros rígidos"
    page_text = f" na tela {context.page}" if context.page != "unknown" else ""
    lines = [
        "Triagem em lote pronta" + page_text + ".",
        f"Analisei {total_candidates} leads com {filter_text} ",
        f"e priorizei {len(items)} para ação.",
        "Top prioridades:",
    ]
    for index, item in enumerate(items[:5], start=1):
        lines.append(
            f"{index}. {item.code} — {item.name} — {item.course_name} "
            f"| {item.status}/{item.priority} | ação: "
            f"{item.recommended_action}"
        )
    lines.append(
        "Nenhuma ação em lote foi executada ainda. "
        "Esta é uma prévia segura para aprovação humana."
    )
    return "\n".join(lines)


def _safe_execution_plan() -> dict[str, Any]:
    return {
        "mode": "preview_only",
        "requires_confirmation": True,
        "executed_actions": [],
        "next_allowed_steps": [
            "registrar atendimento em lote após confirmação",
            "criar retornos em lote após confirmação",
            "exportar plano de atendimento",
        ],
        "safety_notes": [
            "ações em lote exigem revisão humana",
            "não enviar mensagens reais sem consentimento",
            "não acessar gabaritos oficiais do Business Lab",
        ],
    }


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
