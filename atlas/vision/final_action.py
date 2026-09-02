"""Confirmação supervisionada para ações finais do Atlas Vision Etapa 14."""

from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable


@dataclass(frozen=True, slots=True)
class FinalActionRequest:
    target: str
    action: str = "submit"


@dataclass(frozen=True, slots=True)
class PendingFinalAction:
    token: str
    target: str
    action: str
    context_token: str
    dom_index: int
    fingerprint: tuple[tuple[str, str], ...]
    expires_at: datetime

    def fingerprint_dict(self) -> dict[str, str]:
        return dict(self.fingerprint)


class VisionConfirmationError(ValueError):
    pass


_FINAL_ACTION = re.compile(
    r"^\s*(?:por\s+favor\s+)?"
    r"(?:envie|enviar|submeta|submeter|confirme|confirmar)\s+"
    r"(?:(?:o|a)\s+)?(?P<target>formul[aá]rio|bot[aã]o\s+enviar)\s*$",
    flags=re.IGNORECASE,
)

_CONFIRM = re.compile(
    r"^\s*confirmar\s+vis[aã]o\s+(?P<token>[A-Za-z0-9_-]{6,32})\s*$",
    flags=re.IGNORECASE,
)

_SENSITIVE_FINAL_TERMS = {
    "apagar",
    "comprar",
    "deletar",
    "excluir",
    "pagar",
    "publicar",
    "transferir",
}


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def extract_final_action_request(command: str) -> FinalActionRequest | None:
    match = _FINAL_ACTION.match(command.strip())
    if match is None:
        return None

    target = match.group("target").strip().rstrip(" .!?;:")
    normalized = _normalize(target)
    if any(term in normalized for term in _SENSITIVE_FINAL_TERMS):
        return None

    if normalized == "formulario":
        target = "botão enviar"

    return FinalActionRequest(target=target)


def extract_final_action_confirmation(command: str) -> str | None:
    match = _CONFIRM.match(command.strip())
    return match.group("token") if match is not None else None


class VisionConfirmationStore:
    """Mantém uma confirmação curta, vinculada ao DOM e de uso único."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 120.0,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("A validade da confirmação deve ser positiva.")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory or self._new_token
        self._pending: dict[str, PendingFinalAction] = {}
        self._lock = RLock()

    @staticmethod
    def _new_token() -> str:
        return secrets.token_urlsafe(6)

    def prepare(
        self,
        *,
        target: str,
        action: str,
        context_token: str,
        dom_index: int,
        fingerprint: dict[str, str],
    ) -> PendingFinalAction:
        now = self._clock()
        token = self._token_factory().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,32}", token):
            raise ValueError("O gerador produziu um token de confirmação inválido.")

        pending = PendingFinalAction(
            token=token,
            target=target,
            action=action,
            context_token=context_token,
            dom_index=dom_index,
            fingerprint=tuple(sorted(fingerprint.items())),
            expires_at=now + self._ttl,
        )

        with self._lock:
            self._pending.clear()
            self._pending[token] = pending
        return pending

    def consume(self, token: str) -> PendingFinalAction:
        now = self._clock()
        with self._lock:
            pending = self._pending.pop(token, None)

        if pending is None:
            raise VisionConfirmationError(
                "A confirmação não existe ou já foi utilizada."
            )
        if now >= pending.expires_at:
            raise VisionConfirmationError("A confirmação expirou.")
        return pending

    def revoke_all(self) -> None:
        with self._lock:
            self._pending.clear()

