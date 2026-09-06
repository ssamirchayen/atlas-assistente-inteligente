from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Protocol

from atlas.integrations import IntegrationManager, register_default_connectors
from atlas.integrations.base import IntegrationResult

from .batch_leads import looks_like_batch_lead_triage, run_batch_lead_triage
from .batch_messages import (
    looks_like_batch_message_command,
    run_batch_message_workflow,
)
from .models import (
    CopilotActionResult,
    CopilotPageContext,
    CopilotRequest,
    CopilotResponse,
)
from .smart_reports import looks_like_smart_report_command, run_smart_report


class IntegrationExecutor(Protocol):
    def execute(
        self,
        connector_name: str,
        action: str,
        **kwargs: Any,
    ) -> IntegrationResult: ...


class BusinessLabCopilotBridge:
    def __init__(
        self,
        manager: IntegrationExecutor | None = None,
    ) -> None:
        if manager is None:
            register_default_connectors()
            manager = IntegrationManager()
        self.manager = manager

    def handle(self, payload: dict[str, Any]) -> CopilotResponse:
        request = CopilotRequest.from_payload(payload)
        if not request.message:
            return self._error(
                "empty_message",
                "Digite um comando para o Atlas Copilot.",
                request.context,
            )

        intent = self._detect_intent(request.message)
        if intent == "summarize_screen":
            return self._summarize_screen(request)
        if intent == "summarize_lead":
            if not request.context.lead_code:
                if _message_mentions_lead(request.message):
                    return self._missing_lead("summarize_lead", request.context)
                return self._summarize_screen(request)
            return self._summarize_lead(request)
        if intent == "suggest_next_action":
            return self._suggest_next_action(request)
        if intent == "create_interaction":
            return self._create_interaction(request, payload)
        if intent == "create_followup":
            return self._create_followup(request, payload)
        if intent == "list_courses":
            return self._list_courses(request)
        if intent == "dashboard":
            return self._dashboard(request)
        if intent == "batch_lead_triage":
            return run_batch_lead_triage(request, self.manager)
        if intent == "batch_messages":
            return run_batch_message_workflow(request, self.manager, payload)
        if intent == "smart_reports":
            return run_smart_report(request, self.manager)

        return CopilotResponse(
            ok=True,
            intent="help",
            context=request.context,
            answer=(
                "Estou conectado como Copilot local. Nesta etapa posso resumir "
                "um lead aberto, sugerir próxima ação, registrar atendimento, "
                "criar retorno, consultar cursos, ler o dashboard, "
                "fazer triagem em lote de leads, preparar "
                "atendimentos/mensagens em lote, atualizar status "
                "dos leads após confirmação e gerar relatórios inteligentes "
                "de leads, matrículas, atendimentos e retornos."
            ),
            data={
                "examples": [
                    "Resuma esse lead",
                    "Qual a próxima ação desse lead?",
                    "Registre atendimento dizendo que pediu retorno amanhã",
                    "Crie um retorno amanhã às 15h",
                    "Mostre os cursos",
                    "Resumo do dashboard",
                    "Analise os 10 leads novos de Radiologia",
                    "Prepare mensagens para 10 leads de Radiologia",
                    "Registre atendimentos em lote para leads em follow-up",
                    "Crie retornos para 5 leads novos e atualize status para follow_up",
                    "Gere um relatório completo dos leads de Radiologia",
                    "Liste retornos atrasados por prioridade",
                    "Analise atendimentos e diga onde perdemos conversão",
                ]
            },
        )

    def _summarize_screen(
        self,
        request: CopilotRequest,
    ) -> CopilotResponse:
        dashboard_result = self._execute("dashboard")
        leads_result = self._execute("list_leads", limit=10)

        if not dashboard_result.ok:
            return self._result_error(
                "summarize_screen",
                request.context,
                dashboard_result,
            )

        dashboard = _as_dict(dashboard_result.data)
        leads = _as_list(leads_result.data) if leads_result.ok else []
        page_label = _page_label(request.context.page)
        total_leads = _first_value(
            dashboard,
            "total_leads",
            "leads_total",
            "active_leads",
            default="não informado",
        )
        conversion_rate = _first_value(
            dashboard,
            "conversion_rate",
            "taxa_conversao",
            default="não informada",
        )
        pending_followups = _first_value(
            dashboard,
            "pending_followups",
            "followups_pending",
            "retornos_pendentes",
            default="não informado",
        )
        overdue_followups = _first_value(
            dashboard,
            "overdue_followups",
            "followups_overdue",
            "retornos_atrasados",
            default="não informado",
        )
        high_priority = sum(
            1 for lead in leads if str(lead.get("priority") or "") == "alta"
        )
        new_leads = sum(
            1 for lead in leads if str(lead.get("status") or "") == "novo"
        )
        follow_up_leads = sum(
            1 for lead in leads if str(lead.get("status") or "") == "follow_up"
        )

        answer = (
            f"Resumo da tela {page_label}: o Atlas está lendo a visão geral "
            f"do Business Lab. Total de leads reportado: {total_leads}; "
            f"taxa de conversão: {conversion_rate}%; retornos pendentes: "
            f"{pending_followups}; retornos atrasados: {overdue_followups}. "
            f"Na amostra de {len(leads)} lead(s), encontrei {high_priority} "
            f"de prioridade alta, {new_leads} novo(s) e {follow_up_leads} "
            "em follow-up. Próxima ação recomendada: priorizar retornos "
            "atrasados, leads de prioridade alta e oportunidades próximas "
            "de matrícula."
        )

        return CopilotResponse(
            ok=True,
            intent="summarize_screen",
            context=request.context,
            answer=answer,
            actions=(
                _action_result(dashboard_result),
                _action_result(leads_result),
            ),
            data={
                "dashboard": dashboard,
                "lead_sample": leads,
                "screen_summary": {
                    "page": request.context.page,
                    "page_label": page_label,
                    "sample_size": len(leads),
                    "high_priority": high_priority,
                    "new_leads": new_leads,
                    "follow_up_leads": follow_up_leads,
                },
            },
        )

    def _summarize_lead(
        self,
        request: CopilotRequest,
    ) -> CopilotResponse:
        lead_result = self._require_lead_result(request.context)
        if not lead_result.ok:
            return self._result_error(
                "summarize_lead",
                request.context,
                lead_result,
            )

        lead = _as_dict(lead_result.data)
        interactions = self._execute(
            "list_interactions",
            code=request.context.lead_code,
            limit=5,
        )
        followups = self._execute(
            "list_followups",
            code=request.context.lead_code,
        )

        answer = (
            f"Resumo do lead {lead.get('synthetic_code', request.context.lead_code)}: "
            f"{lead.get('name', 'sem nome')} tem interesse em "
            f"{lead.get('course_name', 'curso não informado')}. "
            f"Status atual: {lead.get('status', 'não informado')}; "
            f"prioridade: {lead.get('priority', 'não informada')}. "
            f"Origem: {lead.get('source', 'não informada')}."
        )

        return CopilotResponse(
            ok=True,
            intent="summarize_lead",
            context=request.context,
            answer=answer,
            actions=(
                _action_result(lead_result),
                _action_result(interactions),
                _action_result(followups),
            ),
            data={
                "lead": lead,
                "recent_interactions": interactions.data if interactions.ok else [],
                "followups": followups.data if followups.ok else [],
            },
        )

    def _suggest_next_action(
        self,
        request: CopilotRequest,
    ) -> CopilotResponse:
        lead_result = self._require_lead_result(request.context)
        if not lead_result.ok:
            return self._result_error(
                "suggest_next_action",
                request.context,
                lead_result,
            )

        lead = _as_dict(lead_result.data)
        status = str(lead.get("status") or "")
        priority = str(lead.get("priority") or "")
        suggestion = _suggestion_for_lead(status=status, priority=priority)

        return CopilotResponse(
            ok=True,
            intent="suggest_next_action",
            context=request.context,
            answer=(
                f"Minha sugestão para {lead.get('synthetic_code')}: "
                f"{suggestion}"
            ),
            actions=(_action_result(lead_result),),
            data={
                "lead": lead,
                "suggestion": suggestion,
            },
            requires_human_review=True,
        )

    def _create_interaction(
        self,
        request: CopilotRequest,
        payload: dict[str, Any],
    ) -> CopilotResponse:
        if not request.context.lead_code:
            return self._missing_lead("create_interaction", request.context)

        content = _extract_interaction_content(request.message, payload)
        if request.dry_run:
            return CopilotResponse(
                ok=True,
                intent="create_interaction",
                context=request.context,
                answer=(
                    "Modo simulação: eu registraria um atendimento no lead "
                    f"{request.context.lead_code}: {content}"
                ),
                data={"content": content},
            )

        result = self._execute(
            "create_interaction",
            code=request.context.lead_code,
            channel=str(payload.get("channel") or "WhatsApp"),
            kind=str(payload.get("kind") or "observacao"),
            direction=str(payload.get("direction") or "saida"),
            outcome=str(payload.get("outcome") or "interessado"),
            content=content,
        )

        if not result.ok:
            return self._result_error(
                "create_interaction",
                request.context,
                result,
            )

        return CopilotResponse(
            ok=True,
            intent="create_interaction",
            context=request.context,
            answer=(
                "Atendimento registrado pelo Atlas no lead "
                f"{request.context.lead_code}."
            ),
            actions=(_action_result(result),),
            data={"interaction": result.data},
            requires_human_review=True,
        )

    def _create_followup(
        self,
        request: CopilotRequest,
        payload: dict[str, Any],
    ) -> CopilotResponse:
        if not request.context.lead_code:
            return self._missing_lead("create_followup", request.context)

        title = str(
            payload.get("title")
            or "Retorno criado pelo Atlas Copilot"
        )
        due_at = str(payload.get("due_at") or "").strip()
        if not due_at:
            due_at = _extract_due_at(request.message)

        if not due_at:
            return self._error(
                "missing_due_at",
                (
                    "Para criar retorno, informe data e hora. Exemplo: "
                    "crie retorno amanhã às 15h."
                ),
                request.context,
            )

        notes = str(payload.get("notes") or request.message)
        priority = str(payload.get("priority") or "media")
        if priority == "média":
            priority = "media"

        if request.dry_run:
            return CopilotResponse(
                ok=True,
                intent="create_followup",
                context=request.context,
                answer=(
                    "Modo simulação: eu criaria retorno para "
                    f"{request.context.lead_code} em {due_at}."
                ),
                data={"title": title, "due_at": due_at, "priority": priority},
            )

        result = self._execute(
            "create_followup",
            code=request.context.lead_code,
            title=title,
            notes=notes,
            priority=priority,
            due_at=due_at,
        )
        if not result.ok:
            return self._result_error(
                "create_followup",
                request.context,
                result,
            )

        return CopilotResponse(
            ok=True,
            intent="create_followup",
            context=request.context,
            answer=(
                f"Retorno criado pelo Atlas para {request.context.lead_code} "
                f"em {due_at}."
            ),
            actions=(_action_result(result),),
            data={"followup": result.data},
            requires_human_review=True,
        )

    def _list_courses(
        self,
        request: CopilotRequest,
    ) -> CopilotResponse:
        result = self._execute("list_courses")
        if not result.ok:
            return self._result_error(
                "list_courses",
                request.context,
                result,
            )

        courses = result.data if isinstance(result.data, list) else []
        names = [str(course.get("name")) for course in courses[:8]]
        return CopilotResponse(
            ok=True,
            intent="list_courses",
            context=request.context,
            answer="Cursos ativos: " + ", ".join(names) + ".",
            actions=(_action_result(result),),
            data={"courses": courses},
        )

    def _dashboard(
        self,
        request: CopilotRequest,
    ) -> CopilotResponse:
        result = self._execute("dashboard")
        if not result.ok:
            return self._result_error(
                "dashboard",
                request.context,
                result,
            )

        dashboard = _as_dict(result.data)
        return CopilotResponse(
            ok=True,
            intent="dashboard",
            context=request.context,
            answer=(
                "Dashboard lido pelo Atlas. Use os dados retornados no painel "
                "para destacar leads, matrículas, atendimentos e retornos."
            ),
            actions=(_action_result(result),),
            data={"dashboard": dashboard},
        )

    def _require_lead_result(
        self,
        context: CopilotPageContext,
    ) -> IntegrationResult:
        if not context.lead_code:
            return IntegrationResult(
                ok=False,
                action="get_lead",
                error=(
                    "Nenhum lead aberto. Abra uma página de lead ou envie "
                    "context.lead_code."
                ),
            )
        return self._execute("get_lead", code=context.lead_code)

    def _execute(self, action: str, **kwargs: Any) -> IntegrationResult:
        return self.manager.execute("business_lab", action, **kwargs)

    def _detect_intent(self, message: str) -> str:
        text = _normalize(message)
        if looks_like_batch_message_command(message):
            return "batch_messages"
        if looks_like_batch_lead_triage(message):
            return "batch_lead_triage"
        if looks_like_smart_report_command(message):
            return "smart_reports"
        if any(word in text for word in ("resuma", "resumir", "resumo")):
            if any(word in text for word in ("tela", "pagina", "lista", "painel")):
                return "summarize_screen"
            return "summarize_lead"
        if any(
            word in text
            for word in ("proxima acao", "proxima ação", "suger", "recomenda")
        ):
            return "suggest_next_action"
        if any(word in text for word in ("atendimento", "registre", "registrar")):
            return "create_interaction"
        if any(word in text for word in ("retorno", "agende", "agendar")):
            return "create_followup"
        if any(word in text for word in ("curso", "cursos", "ofertas")):
            return "list_courses"
        if any(word in text for word in ("dashboard", "painel", "indicadores")):
            return "dashboard"
        return "help"

    def _missing_lead(
        self,
        intent: str,
        context: CopilotPageContext,
    ) -> CopilotResponse:
        return self._error(
            intent,
            (
                "Nenhum lead aberto. Abra a tela de um lead ou envie "
                "o código SIM-xxxxx no contexto do widget."
            ),
            context,
        )

    def _result_error(
        self,
        intent: str,
        context: CopilotPageContext,
        result: IntegrationResult,
    ) -> CopilotResponse:
        return self._error(
            intent,
            result.error or "Ação não concluída.",
            context,
            actions=(_action_result(result),),
        )

    def _error(
        self,
        intent: str,
        message: str,
        context: CopilotPageContext,
        *,
        actions: tuple[CopilotActionResult, ...] = (),
    ) -> CopilotResponse:
        return CopilotResponse(
            ok=False,
            intent=intent,
            context=context,
            answer=message,
            error=message,
            actions=actions,
        )


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_value(
    source: dict[str, Any],
    *keys: str,
    default: Any,
) -> Any:
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return default



def _message_mentions_lead(message: str) -> bool:
    text = _normalize(message)
    return any(marker in text for marker in ("lead", "sim-"))

def _page_label(page: str) -> str:
    labels = {
        "index": "Painel principal",
        "leads": "Lista de leads",
        "lead_detail": "Detalhe de lead",
        "interactions": "Atendimentos",
        "followups": "Retornos",
        "enrollments": "Matrículas",
        "reports": "Relatórios",
    }
    return labels.get(page, page or "tela atual")


def _suggestion_for_lead(*, status: str, priority: str) -> str:
    if status == "novo":
        return "fazer primeiro contato e registrar atendimento no histórico."
    if status == "em_atendimento" and priority == "alta":
        return "priorizar contato humano e agendar retorno ainda hoje."
    if status == "follow_up":
        return "verificar retornos pendentes e tentar conversão para matrícula."
    if status == "convertido":
        return "conferir matrícula e status de pagamento."
    if status == "perdido":
        return "registrar motivo da perda e não insistir sem novo interesse."
    return "registrar atendimento e definir um próximo retorno."


def _extract_interaction_content(
    message: str,
    payload: dict[str, Any],
) -> str:
    content = str(payload.get("content") or "").strip()
    if content:
        return content

    lowered = message.lower()
    for marker in ("dizendo que", "informando que", "com a observação", "observacao"):
        index = lowered.find(marker)
        if index >= 0:
            extracted = message[index + len(marker) :].strip(" :.-")
            if extracted:
                return extracted

    return f"Atendimento registrado pelo Atlas Copilot: {message}"


def _extract_due_at(message: str) -> str:
    text = _normalize(message)
    if "amanha" not in text and "amanhã" not in message.lower():
        return ""

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
