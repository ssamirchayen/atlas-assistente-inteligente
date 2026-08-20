from __future__ import annotations

import json

import pytest

from atlas.school import MetaWhatsAppClient, WhatsAppClientError


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self._content = json.dumps(payload).encode("utf-8")

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield self._content


class _Session:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_meta_client_sends_only_official_template_payload() -> None:
    session = _Session(_Response(200, {"messages": [{"id": "wamid.1"}]}))
    client = MetaWhatsAppClient(
        access_token="secret-token",
        graph_version="v26.0",
        session=session,
    )

    message_id = client.send_template(
        phone_number_id="123456789012345",
        recipient_e164="+5592999990001",
        template_name="school_lead_followup",
        language_code="pt_BR",
        body_parameters=("Ana", "Radiologia"),
    )

    assert message_id == "wamid.1"
    url, request = session.calls[0]
    assert url == (
        "https://graph.facebook.com/v26.0/"
        "123456789012345/messages"
    )
    assert request["allow_redirects"] is False
    assert request["headers"]["Authorization"] == "Bearer secret-token"
    assert request["json"]["to"] == "5592999990001"
    assert request["json"]["type"] == "template"
    assert request["json"]["template"]["name"] == (
        "school_lead_followup"
    )


def test_meta_error_is_sanitized() -> None:
    session = _Session(
        _Response(401, {"error": {"message": "token secret-token"}})
    )
    client = MetaWhatsAppClient(
        access_token="secret-token",
        session=session,
    )

    with pytest.raises(WhatsAppClientError) as captured:
        client.send_template(
            phone_number_id="123456789012345",
            recipient_e164="+5592999990001",
            template_name="school_lead_followup",
            language_code="pt_BR",
            body_parameters=("Ana",),
        )

    assert captured.value.code == "provider_http_401"
    assert "secret-token" not in str(captured.value)
