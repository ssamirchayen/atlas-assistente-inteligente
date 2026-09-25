from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LeadRecord:
    name: str
    phone: str | None = None
    email: str | None = None
    interest: str | None = None
    source: str = "internet"
    channel: str = "web"
    campaign: str | None = None
    message: str | None = None
    consent: bool = True
    external_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_phone(self) -> str | None:
        if not self.phone:
            return None
        digits = "".join(ch for ch in self.phone if ch.isdigit())
        return digits or None

    def identity_key(self) -> str:
        phone = self.normalized_phone()
        email = (self.email or "").strip().lower()
        if phone:
            return f"phone:{phone}"
        if email:
            return f"email:{email}"
        external = (self.external_id or "").strip().lower()
        if external:
            return f"external:{external}"
        return f"name:{self.name.strip().lower()}|source:{self.source.strip().lower()}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name.strip(),
            "phone": self.phone,
            "email": self.email,
            "interest": self.interest,
            "source": self.source,
            "channel": self.channel,
            "campaign": self.campaign,
            "message": self.message,
            "consent": self.consent,
            "external_id": self.external_id,
            "metadata": dict(self.metadata),
            "captured_at": utc_now_iso(),
        }


@dataclass(frozen=True)
class LeadCaptureRequest:
    source: str = "internet"
    channel: str = "web"
    campaign: str | None = None
    leads: tuple[LeadRecord, ...] = ()
    auto_triage: bool = True
    prepare_contact: bool = True
    confirm_contact: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "channel": self.channel,
            "campaign": self.campaign,
            "auto_triage": self.auto_triage,
            "prepare_contact": self.prepare_contact,
            "confirm_contact": self.confirm_contact,
            "leads": [lead.to_payload() for lead in self.leads],
        }
