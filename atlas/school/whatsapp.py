"""Cliente mínimo da WhatsApp Business Platform oficial da Meta."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import re
from typing import Protocol

import requests


_GRAPH_VERSION_PATTERN = re.compile(r"^v\d+\.0$")
_PHONE_NUMBER_ID_PATTERN = re.compile(r"^\d{5,32}$")
_E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class WhatsAppClientError(RuntimeError):
    """Erro sanitizado; nunca contém token nem corpo retornado pela Meta."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WhatsAppTemplateClient(Protocol):
    """Contrato usado pelo serviço de contato escolar."""

    @property
    def dry_run(self) -> bool: ...

    def send_template(
        self,
        *,
        phone_number_id: str,
        recipient_e164: str,
        template_name: str,
        language_code: str,
        body_parameters: Sequence[str],
    ) -> str: ...


class DryRunWhatsAppClient:
    """Simulador que não usa rede e não envia mensagens reais."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    @property
    def dry_run(self) -> bool:
        return True

    def send_template(
        self,
        *,
        phone_number_id: str,
        recipient_e164: str,
        template_name: str,
        language_code: str,
        body_parameters: Sequence[str],
    ) -> str:
        _validate_destination(phone_number_id, recipient_e164)
        call = {
            "phone_number_id": phone_number_id,
            "recipient_e164": recipient_e164,
            "template_name": template_name,
            "language_code": language_code,
            "body_parameters": tuple(body_parameters),
        }
        self.calls.append(call)
        fingerprint = json.dumps(
            call,
            ensure_ascii=False,
            sort_keys=True,
            default=list,
        )
        return "dry_" + sha256(fingerprint.encode("utf-8")).hexdigest()[:24]


class MetaWhatsAppClient:
    """Envia somente templates pela Cloud API, sem seguir redirecionamento."""

    def __init__(
        self,
        *,
        access_token: str,
        graph_version: str = "v26.0",
        timeout: float = 15.0,
        session: requests.Session | None = None,
        max_response_bytes: int = 1_000_000,
    ) -> None:
        token = access_token.strip()
        version = graph_version.strip()

        if not token:
            raise ValueError("O token da WhatsApp Business é obrigatório.")
        if not _GRAPH_VERSION_PATTERN.fullmatch(version):
            raise ValueError("A versão da Graph API é inválida.")
        if timeout <= 0:
            raise ValueError("O timeout deve ser positivo.")
        if max_response_bytes <= 0:
            raise ValueError("O limite da resposta deve ser positivo.")

        self._access_token = token
        self._graph_version = version
        self._timeout = timeout
        self._session = session or requests.Session()
        self._max_response_bytes = max_response_bytes

    @property
    def dry_run(self) -> bool:
        return False

    def send_template(
        self,
        *,
        phone_number_id: str,
        recipient_e164: str,
        template_name: str,
        language_code: str,
        body_parameters: Sequence[str],
    ) -> str:
        _validate_destination(phone_number_id, recipient_e164)
        payload = _template_payload(
            recipient_e164=recipient_e164,
            template_name=template_name,
            language_code=language_code,
            body_parameters=body_parameters,
        )
        url = (
            "https://graph.facebook.com/"
            f"{self._graph_version}/{phone_number_id}/messages"
        )

        try:
            response = self._session.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "Atlas-Local/0.22 school-outreach",
                },
                json=payload,
                timeout=self._timeout,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout as error:
            raise WhatsAppClientError(
                "provider_timeout",
                "A WhatsApp Business excedeu o tempo limite.",
            ) from error
        except requests.RequestException as error:
            raise WhatsAppClientError(
                "provider_unavailable",
                "A WhatsApp Business não está disponível.",
            ) from error

        if 300 <= response.status_code < 400:
            raise WhatsAppClientError(
                "provider_redirect_blocked",
                "A Meta tentou redirecionar a solicitação.",
            )
        if response.status_code >= 400:
            raise WhatsAppClientError(
                f"provider_http_{response.status_code}",
                "A Meta rejeitou o envio da mensagem.",
            )

        data = _read_limited_json(
            response,
            max_response_bytes=self._max_response_bytes,
        )
        messages = data.get("messages")

        if not isinstance(messages, list) or not messages:
            raise WhatsAppClientError(
                "provider_invalid_payload",
                "A Meta não confirmou o identificador da mensagem.",
            )

        first = messages[0]
        message_id = first.get("id") if isinstance(first, Mapping) else None

        if not isinstance(message_id, str) or not message_id.strip():
            raise WhatsAppClientError(
                "provider_invalid_payload",
                "A Meta não confirmou o identificador da mensagem.",
            )

        return message_id.strip()


def _template_payload(
    *,
    recipient_e164: str,
    template_name: str,
    language_code: str,
    body_parameters: Sequence[str],
) -> dict[str, object]:
    template: dict[str, object] = {
        "name": template_name,
        "language": {"code": language_code},
    }
    values = tuple(str(value).strip() for value in body_parameters)

    if any(not value for value in values):
        raise ValueError("Os parâmetros do template não podem ser vazios.")

    if values:
        template["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": value} for value in values
                ],
            }
        ]

    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_e164.removeprefix("+"),
        "type": "template",
        "template": template,
    }


def _validate_destination(
    phone_number_id: str,
    recipient_e164: str,
) -> None:
    if not _PHONE_NUMBER_ID_PATTERN.fullmatch(phone_number_id.strip()):
        raise ValueError("phone_number_id corporativo inválido.")
    if not _E164_PATTERN.fullmatch(recipient_e164.strip()):
        raise ValueError("O destinatário deve estar no formato E.164.")


def _read_limited_json(
    response: requests.Response,
    *,
    max_response_bytes: int,
) -> Mapping[str, object]:
    declared = response.headers.get("Content-Length")

    if declared:
        try:
            if int(declared) > max_response_bytes:
                raise WhatsAppClientError(
                    "provider_response_too_large",
                    "A resposta da Meta excedeu o limite.",
                )
        except ValueError as error:
            raise WhatsAppClientError(
                "provider_invalid_headers",
                "A Meta retornou cabeçalhos inválidos.",
            ) from error

    content = bytearray()

    for chunk in response.iter_content(chunk_size=65_536):
        content.extend(chunk)

        if len(content) > max_response_bytes:
            raise WhatsAppClientError(
                "provider_response_too_large",
                "A resposta da Meta excedeu o limite.",
            )

    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WhatsAppClientError(
            "provider_invalid_json",
            "A Meta retornou uma resposta inválida.",
        ) from error

    if not isinstance(payload, Mapping):
        raise WhatsAppClientError(
            "provider_invalid_payload",
            "A Meta retornou uma resposta inválida.",
        )

    return payload
