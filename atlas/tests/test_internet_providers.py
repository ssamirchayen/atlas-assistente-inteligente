from __future__ import annotations

from collections.abc import Mapping

import pytest
import requests

from atlas.internet.http import RequestsJsonClient
from atlas.internet.models import SearchFreshness, WebSearchRequest
from atlas.internet.provider import SearchProviderError
from atlas.internet.providers import (
    BraveSearchProvider,
    SearxngSearchProvider,
    WikipediaSearchProvider,
)


class StubJsonClient:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        headers: Mapping[str, str] | None = None,
        timeout: float,
    ) -> Mapping[str, object]:
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        return self.payload


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def test_wikipedia_maps_articles_to_traceable_results() -> None:
    client = StubJsonClient(
        {
            "query": {
                "pages": [
                    {
                        "title": "Inteligência artificial",
                        "fullurl": "https://pt.wikipedia.org/wiki/IA",
                        "extract": "Área da computação.",
                    }
                ]
            }
        }
    )
    provider = WikipediaSearchProvider(client)

    results = provider.search(WebSearchRequest("inteligência artificial"), limit=5)

    assert len(results) == 1
    assert results[0].provider_id == "wikipedia.pt"
    assert results[0].source_name == "Wikipédia"
    assert client.calls[0]["params"]["generator"] == "search"


def test_brave_sends_key_only_in_header_and_maps_freshness() -> None:
    client = StubJsonClient(
        {
            "web": {
                "results": [
                    {
                        "title": "Atlas",
                        "url": "https://example.com/atlas",
                        "description": "Assistente local.",
                        "profile": {"long_name": "Example"},
                    }
                ]
            }
        }
    )
    provider = BraveSearchProvider(client, api_key="private-key")
    request = WebSearchRequest(
        "Atlas assistente",
        freshness=SearchFreshness.WEEK,
    )

    results = provider.search(request, limit=5)
    call = client.calls[0]

    assert results[0].provider_id == "brave.web"
    assert call["headers"]["X-Subscription-Token"] == "private-key"
    assert call["params"]["freshness"] == "pw"
    assert "private-key" not in repr(provider)


def test_searxng_maps_underlying_engines_and_uses_json_format() -> None:
    client = StubJsonClient(
        {
            "results": [
                {
                    "title": "Resultado",
                    "url": "https://example.org/result",
                    "content": "Resumo",
                    "engines": ["brave", "bing"],
                }
            ]
        }
    )
    provider = SearxngSearchProvider(
        client,
        base_url="http://localhost:8080",
    )

    results = provider.search(WebSearchRequest("resultado"), limit=5)

    assert results[0].source_name == "brave, bing"
    assert client.calls[0]["url"] == "http://localhost:8080/search"
    assert client.calls[0]["params"]["format"] == "json"


@pytest.mark.parametrize(
    "url",
    [
        "http://search.example.com",
        "ftp://search.example.com",
        "http://192.168.1.10",
    ],
)
def test_searxng_rejects_unsafe_endpoint_by_default(url: str) -> None:
    with pytest.raises(ValueError):
        SearxngSearchProvider(StubJsonClient({}), base_url=url)


def test_searxng_private_endpoint_requires_explicit_opt_in() -> None:
    provider = SearxngSearchProvider(
        StubJsonClient({"results": []}),
        base_url="http://192.168.1.10",
        allow_private_endpoint=True,
    )

    assert provider.search(WebSearchRequest("teste"), limit=5) == ()


def test_http_client_blocks_redirect_and_oversized_payload() -> None:
    redirect_client = RequestsJsonClient(
        session=FakeSession(FakeResponse(b"{}", status_code=302))
    )
    oversized_client = RequestsJsonClient(
        session=FakeSession(
            FakeResponse(b"{}", headers={"Content-Length": "100"})
        ),
        max_response_bytes=10,
    )

    with pytest.raises(SearchProviderError) as redirect:
        redirect_client.get_json(
            "https://provider.example/api",
            params={},
            timeout=1,
        )

    with pytest.raises(SearchProviderError) as oversized:
        oversized_client.get_json(
            "https://provider.example/api",
            params={},
            timeout=1,
        )

    assert redirect.value.code == "provider_redirect_blocked"
    assert oversized.value.code == "provider_response_too_large"


def test_http_client_sanitizes_network_timeout() -> None:
    class TimeoutSession:
        def get(self, *args: object, **kwargs: object) -> None:
            raise requests.Timeout("raw provider details")

    client = RequestsJsonClient(session=TimeoutSession())

    with pytest.raises(SearchProviderError) as captured:
        client.get_json(
            "https://provider.example/api",
            params={},
            timeout=1,
        )

    assert captured.value.code == "provider_timeout"
    assert "raw provider details" not in str(captured.value)
