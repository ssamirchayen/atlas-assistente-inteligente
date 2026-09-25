from __future__ import annotations

import math
import os
import re
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests

CONTRACT_NAME = "nexyra-crm-atlas"
CONTRACT_VERSION = "1.0"
API_PREFIX = "/api/v1/integrations/atlas"
SUPPORTED_ACTIONS = frozenset(
    {
        "lead.update",
        "opportunity.move",
        "activity.create",
        "activity.complete",
        "lead.assign",
        "lead.prioritize",
        "lead.followup",
        "distribution.run",
    }
)


class NexyraError(ValueError):
    """Erro seguro para exibição: nunca inclui credenciais ou corpo remoto."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class NexyraActionRequest:
    """Pedido imutável que pode ser pré-visualizado e depois confirmado."""

    action: str
    target_public_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class NexyraActionPreview:
    request: NexyraActionRequest
    contract_version: str
    action: str
    target_public_id: str | None
    allowed: bool
    confirmation_required: bool
    summary: str
    normalized_payload: dict[str, object]
    fingerprint: str


@dataclass(frozen=True)
class NexyraConfig:
    base_url: str
    token: str = field(repr=False)
    workspace_id: str
    actor_user_id: str
    timeout: float = 10.0

    @classmethod
    def from_env(cls) -> NexyraConfig:
        try:
            timeout = float(os.getenv("ATLAS_NEXYRA_TIMEOUT", "10"))
        except ValueError:
            raise NexyraError(
                "configuration", "ATLAS_NEXYRA_TIMEOUT deve ser um número."
            ) from None
        config = cls(
            base_url=os.getenv("ATLAS_NEXYRA_URL", "").strip().rstrip("/"),
            token=os.getenv("ATLAS_NEXYRA_TOKEN", "").strip(),
            workspace_id=os.getenv("ATLAS_NEXYRA_WORKSPACE_ID", "").strip(),
            actor_user_id=os.getenv("ATLAS_NEXYRA_ACTOR_USER_ID", "").strip(),
            timeout=timeout,
        )
        config.validate()
        return config

    def validate(self) -> None:
        fields = {
            "ATLAS_NEXYRA_URL": self.base_url,
            "ATLAS_NEXYRA_TOKEN": self.token,
            "ATLAS_NEXYRA_WORKSPACE_ID": self.workspace_id,
            "ATLAS_NEXYRA_ACTOR_USER_ID": self.actor_user_id,
        }
        missing = [name for name, value in fields.items() if not value.strip()]
        if missing:
            raise NexyraError(
                "configuration", "Configure no Atlas: " + ", ".join(missing) + "."
            )
        try:
            url = urlsplit(self.base_url)
            port = url.port
        except ValueError:
            raise NexyraError("configuration", "URL do Nexyra inválida.") from None
        del port
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
            or any(c.isspace() for c in self.base_url)
        ):
            raise NexyraError(
                "configuration",
                "Use a URL raiz do backend Nexyra, sem /api, credenciais ou parâmetros.",
            )
        if url.scheme == "http" and url.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise NexyraError(
                "configuration",
                "Use HTTPS para o Nexyra remoto; HTTP é aceito em localhost.",
            )
        for value in (self.workspace_id, self.actor_user_id):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
                raise NexyraError(
                    "configuration",
                    "Informe os IDs públicos da empresa e do usuário do Nexyra.",
                )
        if not self.token.isascii() or any(c.isspace() for c in self.token):
            raise NexyraError(
                "configuration", "O token do Nexyra contém caracteres inválidos."
            )
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 60:
            raise NexyraError(
                "configuration",
                "ATLAS_NEXYRA_TIMEOUT deve ser maior que zero e no máximo 60 segundos.",
            )


def _invalid() -> NexyraError:
    return NexyraError(
        "invalid_response",
        "O Nexyra retornou dados incompatíveis com o contrato esperado.",
    )


def _version(data: dict, *, named: bool = False) -> None:
    if data.get("contract_version") != CONTRACT_VERSION or (
        named and data.get("contract_name") != CONTRACT_NAME
    ):
        raise NexyraError(
            "incompatible_contract",
            "Contrato Nexyra incompatível. Este conector exige nexyra-crm-atlas 1.0.",
        )


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _count(value: object) -> bool:
    return type(value) is int and value >= 0


def _number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return False
    try:
        return Decimal(str(value)).is_finite()
    except InvalidOperation:
        return False


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise NexyraError(
            "invalid_request", "O payload da ação precisa ser JSON válido."
        ) from None


def _fingerprint(
    request: NexyraActionRequest,
    normalized_payload: dict[str, object],
    summary: str,
) -> str:
    material = _canonical_json(
        {
            "action": request.action,
            "target_public_id": request.target_public_id,
            "payload": normalized_payload,
            "reason": request.reason,
            "summary": summary,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class NexyraClient:
    def __init__(self, config: NexyraConfig) -> None:
        config.validate()
        self.config = config

    def _get(self, path: str, *, authenticated: bool = True) -> dict:
        headers = {"Accept": "application/json"}
        if authenticated:
            headers.update(
                {
                    "X-Nexyra-Integration-Token": self.config.token,
                    "X-Nexyra-Actor-User": self.config.actor_user_id,
                }
            )
        try:
            # Sem redirecionamento, netrc, repetição ou sessão compartilhada.
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(
                    self.config.base_url.rstrip("/") + API_PREFIX + path,
                    headers=headers,
                    timeout=self.config.timeout,
                    allow_redirects=False,
                )
        except requests.Timeout:
            raise NexyraError(
                "timeout",
                "O Nexyra demorou para responder. Confira o backend e tente novamente.",
            ) from None
        except requests.RequestException:
            raise NexyraError(
                "unavailable",
                "Não foi possível conectar ao Nexyra. Confira a URL e se o backend está ativo.",
            ) from None
        errors = {
            401: ("unauthorized", "Token de integração Nexyra inválido ou expirado."),
            403: (
                "forbidden",
                "Usuário sem acesso ativo à empresa ou sem a permissão atlas.use.",
            ),
            404: (
                "not_found",
                "Empresa ou rota Atlas não encontrada no Nexyra. Confira o ID e a versão do backend.",
            ),
            422: (
                "invalid_request",
                "O Nexyra rejeitou a configuração da consulta. Confira os IDs e o contrato.",
            ),
            429: (
                "rate_limited",
                "O Nexyra limitou as consultas. Aguarde antes de tentar novamente.",
            ),
        }
        if response.status_code in errors:
            raise NexyraError(*errors[response.status_code])
        if 300 <= response.status_code < 400:
            raise NexyraError(
                "redirect",
                "A URL do Nexyra redirecionou a consulta. Configure o endereço final do backend.",
            )
        if response.status_code != 200:
            raise NexyraError(
                "server_error", "O Nexyra não concluiu a consulta. Verifique o backend."
            )
        try:
            data = response.json()
        except ValueError:
            raise _invalid() from None
        if not isinstance(data, dict):
            raise _invalid()
        return data

    def _post(self, path: str, payload: dict[str, object]) -> dict:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Nexyra-Integration-Token": self.config.token,
            "X-Nexyra-Actor-User": self.config.actor_user_id,
        }
        try:
            # Uma escrita nunca segue redirecionamento nem é repetida pelo cliente.
            with requests.Session() as session:
                session.trust_env = False
                response = session.post(
                    self.config.base_url.rstrip("/") + API_PREFIX + path,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout,
                    allow_redirects=False,
                )
        except requests.Timeout:
            raise NexyraError(
                "timeout",
                "O Nexyra demorou para responder. A ação não será repetida automaticamente; confira o CRM antes de tentar novamente.",
            ) from None
        except requests.RequestException:
            raise NexyraError(
                "unavailable",
                "Não foi possível conectar ao Nexyra. Confira o CRM antes de tentar novamente.",
            ) from None

        errors = {
            401: ("unauthorized", "Token de integração Nexyra inválido ou expirado."),
            403: (
                "forbidden",
                "Usuário sem acesso à empresa ou sem a permissão necessária.",
            ),
            404: (
                "not_found",
                "Alvo, empresa ou rota de ação não encontrado no Nexyra.",
            ),
            409: (
                "conflict",
                "O Nexyra recusou a execução por conflito ou confirmação inválida.",
            ),
            422: ("invalid_request", "O Nexyra rejeitou os dados da ação."),
            429: (
                "rate_limited",
                "O Nexyra limitou a ação. Confira o CRM antes de tentar novamente.",
            ),
        }
        if response.status_code in errors:
            raise NexyraError(*errors[response.status_code])
        if 300 <= response.status_code < 400:
            raise NexyraError(
                "redirect",
                "A URL do Nexyra redirecionou a ação. Configure o endereço final do backend.",
            )
        if response.status_code != 200:
            raise NexyraError(
                "server_error",
                "O Nexyra não concluiu a ação. Confira o CRM antes de tentar novamente.",
            )
        try:
            data = response.json()
        except ValueError:
            raise _invalid() from None
        if not isinstance(data, dict):
            raise _invalid()
        return data

    @staticmethod
    def _normalize_action_request(
        request: NexyraActionRequest,
    ) -> NexyraActionRequest:
        action = request.action.strip().lower()
        if action not in SUPPORTED_ACTIONS:
            raise NexyraError(
                "invalid_request", "Ação não suportada pelo contrato Nexyra."
            )
        target = request.target_public_id
        if target is not None:
            target = target.strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", target):
                raise NexyraError(
                    "invalid_request", "O alvo da ação não é um ID público válido."
                )
        target_required = action not in {"activity.create", "distribution.run"}
        if target_required and target is None:
            raise NexyraError(
                "invalid_request", f"A ação {action} exige um ID público alvo."
            )
        if not target_required and target is not None:
            message = (
                "activity.create não aceita alvo separado; use lead_public_id "
                "ou opportunity_public_id no payload."
                if action == "activity.create"
                else "distribution.run não aceita alvo separado."
            )
            raise NexyraError("invalid_request", message)
        if not isinstance(request.payload, dict):
            raise NexyraError(
                "invalid_request", "O payload da ação precisa ser um objeto JSON."
            )
        reason = request.reason.strip() if request.reason is not None else None
        if reason == "":
            reason = None
        if reason is not None and len(reason) > 500:
            raise NexyraError(
                "invalid_request", "O motivo da ação pode ter no máximo 500 caracteres."
            )
        serialized = _canonical_json(request.payload)
        if len(serialized.encode("utf-8")) > 64 * 1024:
            raise NexyraError(
                "invalid_request", "O payload da ação excede o limite seguro de 64 KB."
            )
        return NexyraActionRequest(action, target, dict(request.payload), reason)

    @staticmethod
    def _parse_preview(
        request: NexyraActionRequest,
        data: dict,
    ) -> NexyraActionPreview:
        _version(data)
        expected = {
            "action": request.action,
            "target_public_id": request.target_public_id,
        }
        if any(data.get(key) != value for key, value in expected.items()):
            raise NexyraError(
                "invalid_response",
                "A prévia retornada não corresponde à ação solicitada.",
            )
        if (
            data.get("allowed") is not True
            or data.get("confirmation_required") is not True
        ):
            raise NexyraError(
                "forbidden",
                "O Nexyra não autorizou esta ação ou não exigiu confirmação.",
            )
        summary = data.get("summary")
        normalized = data.get("normalized_payload")
        if (
            not isinstance(summary, str)
            or not summary.strip()
            or not isinstance(normalized, dict)
        ):
            raise _invalid()
        normalized_request = NexyraActionRequest(
            request.action,
            request.target_public_id,
            dict(normalized),
            request.reason,
        )
        return NexyraActionPreview(
            request=normalized_request,
            contract_version=data["contract_version"],
            action=data["action"],
            target_public_id=data["target_public_id"],
            allowed=True,
            confirmation_required=True,
            summary=summary.strip(),
            normalized_payload=dict(normalized),
            fingerprint=_fingerprint(
                normalized_request,
                dict(normalized),
                summary.strip(),
            ),
        )

    def preview_action(
        self,
        request: NexyraActionRequest,
    ) -> NexyraActionPreview:
        normalized_request = self._normalize_action_request(request)
        data = self._post(
            f"/workspaces/{self.config.workspace_id}/actions/preview",
            {
                "action": normalized_request.action,
                "target_public_id": normalized_request.target_public_id,
                "payload": normalized_request.payload,
                "reason": normalized_request.reason,
            },
        )
        return self._parse_preview(normalized_request, data)

    def execute_action(self, preview: NexyraActionPreview) -> dict:
        if not preview.allowed or not preview.confirmation_required:
            raise NexyraError(
                "confirmation_required",
                "A ação só pode ser executada após uma prévia autorizada.",
            )
        # Revalida o alvo e os dados no CRM imediatamente antes da escrita.
        latest = self.preview_action(preview.request)
        if latest.fingerprint != preview.fingerprint:
            raise NexyraError(
                "preview_changed",
                "A prévia mudou no Nexyra; nada foi alterado. Solicite uma nova prévia.",
            )
        data = self._post(
            f"/workspaces/{self.config.workspace_id}/actions/execute",
            {
                "action": latest.action,
                "target_public_id": latest.target_public_id,
                "payload": latest.normalized_payload,
                "reason": latest.request.reason,
                "confirmed": True,
            },
        )
        _version(data)
        if (
            data.get("action") != latest.action
            or data.get("target_public_id") != latest.target_public_id
            or data.get("executed") is not True
            or not isinstance(data.get("result"), dict)
        ):
            raise _invalid()
        return data

    def health(self) -> dict:
        data = self._get("/health", authenticated=False)
        _version(data, named=True)
        if data.get("ok") is not True:
            raise NexyraError(
                "unhealthy", "O Nexyra informou que a integração está indisponível."
            )
        if not all(
            isinstance(data.get(key), str) for key in ("product", "crm_version")
        ):
            raise _invalid()
        return data

    def capabilities(self) -> dict:
        data = self._get("/capabilities")
        _version(data, named=True)
        if not _strings(data.get("capabilities")) or not _strings(
            data.get("supported_actions")
        ):
            raise _invalid()
        if "workspace_context" not in data["capabilities"]:
            raise NexyraError(
                "missing_capability",
                "O Nexyra não oferece consulta de contexto da empresa.",
            )
        return data

    def _context(self) -> dict:
        data = self._get(f"/workspaces/{self.config.workspace_id}/context")
        _version(data)
        for key in ("workspace", "actor", "counts", "opportunity_metrics"):
            if not isinstance(data.get(key), dict):
                raise _invalid()
        workspace, actor = data["workspace"], data["actor"]
        if (
            workspace.get("public_id") != self.config.workspace_id
            or actor.get("user_public_id") != self.config.actor_user_id
        ):
            raise NexyraError(
                "identity_mismatch",
                "A resposta do Nexyra não corresponde à empresa e ao usuário configurados.",
            )
        if not all(
            isinstance(item, str)
            for item in (workspace.get("name"), actor.get("name"), actor.get("role"))
        ):
            raise _invalid()
        if workspace.get("active") is not True:
            raise NexyraError("inactive_workspace", "A empresa está inativa no Nexyra.")
        if not _strings(actor.get("permissions")):
            raise _invalid()
        if "atlas.use" not in actor["permissions"]:
            raise NexyraError(
                "forbidden", "O usuário não possui a permissão atlas.use no Nexyra."
            )
        if not all(
            _count(data["counts"].get(key))
            for key in ("leads", "active_leads", "opportunities", "pending_followups")
        ):
            raise _invalid()
        metrics = data["opportunity_metrics"]
        for key in (
            "total_opportunities",
            "open_opportunities",
            "won_opportunities",
            "lost_opportunities",
        ):
            if not _count(metrics.get(key)):
                raise _invalid()
        for key in (
            "conversion_rate",
            "total_pipeline_value",
            "won_value",
            "average_won_value",
        ):
            if not _number(metrics.get(key)):
                raise _invalid()
        pending = data.get("pending_followups")
        sources = data.get("lead_sources")
        if not isinstance(pending, list) or not isinstance(sources, list):
            raise _invalid()
        if len(pending) > 25 or len(pending) > data["counts"]["pending_followups"]:
            raise _invalid()
        for item in pending:
            if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) for key in ("public_id", "title")
            ):
                raise _invalid()
            if type(item.get("overdue")) is not bool or not (
                item.get("due_at") is None or isinstance(item["due_at"], str)
            ):
                raise _invalid()
        for item in sources:
            if (
                not isinstance(item, dict)
                or not all(
                    isinstance(item.get(key), str) for key in ("source", "channel")
                )
                or not _count(item.get("lead_count"))
            ):
                raise _invalid()
        return data


    def operations(self, *, period_days: int = 30, limit: int = 100) -> dict:
        if not 7 <= period_days <= 365:
            raise NexyraError(
                "invalid_request", "O período operacional deve ficar entre 7 e 365 dias."
            )
        if not 1 <= limit <= 200:
            raise NexyraError(
                "invalid_request", "O limite operacional deve ficar entre 1 e 200 leads."
            )
        try:
            data = self._get(
                f"/workspaces/{self.config.workspace_id}/operations"
                f"?period_days={period_days}&limit={limit}"
            )
        except NexyraError as exc:
            if exc.code == "not_found":
                raise NexyraError(
                    "missing_capability",
                    "A inteligência operacional exige a edição Nexyra + Atlas. "
                    "O Nexyra padrão permanece independente e não expõe esta rota.",
                ) from None
            if exc.code == "forbidden":
                raise NexyraError(
                    "forbidden",
                    "A inteligência operacional exige um usuário Nexyra com analytics.read (gerente ou administrador).",
                ) from None
            raise
        _version(data)
        if not isinstance(data.get("generated_at"), str):
            raise _invalid()
        for key in ("distribution", "sla", "recommendations", "dashboard"):
            if not isinstance(data.get(key), dict):
                raise _invalid()

        distribution = data["distribution"]
        if (
            type(distribution.get("enabled")) is not bool
            or not isinstance(distribution.get("strategy"), str)
            or not _count(distribution.get("total_active_leads"))
            or not _count(distribution.get("unassigned_active_leads"))
            or not isinstance(distribution.get("members"), list)
        ):
            raise _invalid()
        for member in distribution["members"]:
            if (
                not isinstance(member, dict)
                or not all(
                    isinstance(member.get(name), str)
                    for name in ("user_public_id", "name", "role")
                )
                or type(member.get("eligible")) is not bool
                or not _count(member.get("assigned_active_leads"))
            ):
                raise _invalid()

        sla = data["sla"]
        if not isinstance(sla.get("metrics"), dict) or not isinstance(
            sla.get("items"), list
        ):
            raise _invalid()
        for key in (
            "total_attention",
            "awaiting_first_contact",
            "sla_warning",
            "sla_breached",
            "overdue_followups",
            "due_soon_followups",
            "stale_leads",
            "unassigned",
        ):
            if not _count(sla["metrics"].get(key)):
                raise _invalid()
        if len(sla["items"]) > limit:
            raise _invalid()
        for item in sla["items"]:
            if (
                not isinstance(item, dict)
                or not all(
                    isinstance(item.get(name), str)
                    for name in (
                        "lead_public_id",
                        "lead_name",
                        "status",
                        "priority",
                        "source",
                        "sla_state",
                    )
                )
                or not _count(item.get("age_minutes"))
                or not _count(item.get("overdue_followups"))
                or type(item.get("stale")) is not bool
                or type(item.get("score")) is not int
                or not _strings(item.get("reasons"))
            ):
                raise _invalid()

        recommendations = data["recommendations"]
        if not isinstance(recommendations.get("metrics"), dict) or not isinstance(
            recommendations.get("items"), list
        ):
            raise _invalid()
        for key in (
            "total_leads",
            "critical",
            "high",
            "medium",
            "low",
            "awaiting_reply",
            "overdue_followups",
            "unassigned",
            "opportunities_at_risk",
        ):
            if not _count(recommendations["metrics"].get(key)):
                raise _invalid()
        if len(recommendations["items"]) > limit:
            raise _invalid()
        for item in recommendations["items"]:
            if (
                not isinstance(item, dict)
                or not all(
                    isinstance(item.get(name), str)
                    for name in (
                        "lead_public_id",
                        "lead_name",
                        "action",
                        "action_title",
                        "urgency",
                        "suggested_channel",
                    )
                )
                or type(item.get("score")) is not int
                or not _strings(item.get("reasons"))
            ):
                raise _invalid()

        dashboard = data["dashboard"]
        for key in (
            "active_leads",
            "leads_created",
            "unassigned_leads",
            "open_opportunities",
            "pending_activities",
            "overdue_activities",
        ):
            if not _count(dashboard.get(key)):
                raise _invalid()
        if not isinstance(dashboard.get("sla"), dict) or not isinstance(
            dashboard.get("recommendations"), dict
        ):
            raise _invalid()
        if not isinstance(dashboard.get("bottlenecks"), list) or not isinstance(
            dashboard.get("member_performance"), list
        ):
            raise _invalid()
        return data

    def snapshot(self) -> dict:
        """Valida servidor, token, capacidades e identidade em cada consulta."""
        health = self.health()
        capabilities = self.capabilities()
        context = self._context()
        return {"health": health, "capabilities": capabilities, "context": context}
