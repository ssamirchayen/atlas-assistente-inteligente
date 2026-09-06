from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CopilotPageContext:
    page: str = "unknown"
    route: str = ""
    lead_code: str = ""
    enrollment_code: str = ""
    user_email: str = ""
    selected_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CopilotPageContext:
        raw_context = payload.get("context")
        context = raw_context if isinstance(raw_context, dict) else {}
        metadata = context.get("metadata")
        return cls(
            page=str(context.get("page") or context.get("screen") or "unknown"),
            route=str(context.get("route") or context.get("path") or ""),
            lead_code=str(context.get("lead_code") or "").strip().upper(),
            enrollment_code=str(
                context.get("enrollment_code") or ""
            ).strip().upper(),
            user_email=str(context.get("user_email") or "").strip(),
            selected_text=str(context.get("selected_text") or "").strip(),
            metadata=metadata if isinstance(metadata, dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "route": self.route,
            "lead_code": self.lead_code,
            "enrollment_code": self.enrollment_code,
            "user_email": self.user_email,
            "selected_text": self.selected_text,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class CopilotRequest:
    message: str
    context: CopilotPageContext
    dry_run: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> CopilotRequest:
        raw_dry_run = payload.get("dry_run", False)
        return cls(
            message=str(payload.get("message") or "").strip(),
            context=CopilotPageContext.from_payload(payload),
            dry_run=bool(raw_dry_run),
        )


@dataclass(frozen=True, slots=True)
class CopilotActionResult:
    action: str
    ok: bool
    driver: str | None = None
    error: str | None = None
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "ok": self.ok,
            "driver": self.driver,
            "error": self.error,
            "data": self.data,
        }


@dataclass(frozen=True, slots=True)
class CopilotResponse:
    ok: bool
    answer: str
    intent: str = "unknown"
    context: CopilotPageContext | None = None
    actions: tuple[CopilotActionResult, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    requires_human_review: bool = False

    def to_api_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "data": {
                "answer": self.answer,
                "intent": self.intent,
                "context": (
                    self.context.to_dict()
                    if self.context is not None
                    else None
                ),
                "actions": [action.to_dict() for action in self.actions],
                "data": self.data,
                "requires_human_review": self.requires_human_review,
            },
            "meta": {
                "source": "ATLAS_COPILOT_BRIDGE_LOCAL",
                "mode": "local_only",
            },
        }
        if self.error:
            payload["error"] = {
                "code": self.intent,
                "message": self.error,
            }
        return payload
