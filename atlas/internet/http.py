"""Cliente HTTP JSON com limites explícitos para provedores de pesquisa."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Protocol

import requests

from atlas.internet.provider import SearchProviderError


class JsonHttpClient(Protocol):
    """Superfície mínima usada pelos adaptadores de busca."""

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
        timeout: float,
    ) -> Mapping[str, object]: ...


class RequestsJsonClient:
    """Baixa somente JSON limitado e não segue redirecionamentos."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        if max_response_bytes <= 0:
            raise ValueError("O limite da resposta deve ser positivo.")

        self._session = session or requests.Session()
        self._max_response_bytes = max_response_bytes

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
        timeout: float,
    ) -> Mapping[str, object]:
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "Atlas-Local/0.20 web-search",
        }
        request_headers.update(headers or {})

        try:
            response = self._session.get(
                url,
                params=dict(params),
                headers=request_headers,
                timeout=timeout,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout as error:
            raise SearchProviderError(
                "provider_timeout",
                "A fonte excedeu o tempo limite.",
            ) from error
        except requests.RequestException as error:
            raise SearchProviderError(
                "provider_unavailable",
                "A fonte não está disponível.",
            ) from error

        if 300 <= response.status_code < 400:
            raise SearchProviderError(
                "provider_redirect_blocked",
                "A fonte tentou redirecionar a consulta.",
            )

        if response.status_code >= 400:
            raise SearchProviderError(
                f"provider_http_{response.status_code}",
                "A fonte rejeitou a consulta.",
            )

        declared_length = response.headers.get("Content-Length")

        if declared_length and int(declared_length) > self._max_response_bytes:
            raise SearchProviderError(
                "provider_response_too_large",
                "A resposta da fonte excedeu o limite.",
            )

        content = bytearray()

        for chunk in response.iter_content(chunk_size=65_536):
            content.extend(chunk)

            if len(content) > self._max_response_bytes:
                raise SearchProviderError(
                    "provider_response_too_large",
                    "A resposta da fonte excedeu o limite.",
                )

        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SearchProviderError(
                "provider_invalid_json",
                "A fonte retornou um formato inválido.",
            ) from error

        if not isinstance(payload, Mapping):
            raise SearchProviderError(
                "provider_invalid_payload",
                "A fonte não retornou um objeto JSON.",
            )

        return payload
