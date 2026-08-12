from __future__ import annotations

from collections import deque
from typing import Any

import pytest
import requests

from atlas.memory.embeddings import (
    EmbeddingResponseError,
    EmbeddingServiceError,
    EmbeddingUnavailableError,
    OllamaEmbeddingService,
)


class FakeResponse:
    def __init__(
        self,
        payload: Any = None,
        *,
        error: Exception | None = None,
        invalid_json: bool = False,
    ) -> None:
        self.payload = payload
        self.error = error
        self.invalid_json = invalid_json

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> Any:
        if self.invalid_json:
            raise ValueError("JSON inválido")

        return self.payload


class FakeSession:
    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self.responses = deque(responses)
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        response = self.responses.popleft()

        if isinstance(response, Exception):
            raise response

        return response

    def close(self) -> None:
        self.closed = True


def make_service(
    session: FakeSession,
    **kwargs: Any,
) -> OllamaEmbeddingService:
    return OllamaEmbeddingService(
        url="http://localhost:11434/api/embed",
        model="qwen3-embedding:0.6b",
        timeout=12,
        session=session,  # type: ignore[arg-type]
        **kwargs,
    )


def test_embed_single_text_uses_official_ollama_payload() -> None:
    session = FakeSession(
        FakeResponse({"embeddings": [[0.1, 0.2, 0.3]]})
    )
    service = make_service(session)

    result = service.embed("  carros   usados  ")

    assert result.text == "carros usados"
    assert result.values == (0.1, 0.2, 0.3)
    assert result.dimensions == 3
    assert result.model == "qwen3-embedding:0.6b"
    assert result.cached is False
    assert session.calls == [
        {
            "url": "http://localhost:11434/api/embed",
            "json": {
                "model": "qwen3-embedding:0.6b",
                "input": ["carros usados"],
                "truncate": True,
            },
            "timeout": 12.0,
        }
    ]


def test_embed_many_preserves_order_and_deduplicates_request() -> None:
    session = FakeSession(
        FakeResponse({"embeddings": [[1.0, 0.0], [0.0, 1.0]]})
    )
    service = make_service(session)

    results = service.embed_many(["primeiro", "segundo", "primeiro"])

    assert [result.text for result in results] == [
        "primeiro",
        "segundo",
        "primeiro",
    ]
    assert [result.values for result in results] == [
        (1.0, 0.0),
        (0.0, 1.0),
        (1.0, 0.0),
    ]
    assert session.calls[0]["json"]["input"] == ["primeiro", "segundo"]


def test_cache_avoids_second_http_request() -> None:
    session = FakeSession(FakeResponse({"embeddings": [[0.4, 0.6]]}))
    service = make_service(session)

    first = service.embed("mesmo texto")
    second = service.embed("mesmo texto")
    info = service.cache_info()

    assert first.cached is False
    assert second.cached is True
    assert len(session.calls) == 1
    assert info.size == 1
    assert info.hits == 1
    assert info.misses == 1
    assert info.dimensions == 2


def test_cache_evicts_least_recently_used_text() -> None:
    session = FakeSession(
        FakeResponse({"embeddings": [[1.0]]}),
        FakeResponse({"embeddings": [[2.0]]}),
        FakeResponse({"embeddings": [[3.0]]}),
    )
    service = make_service(session, cache_size=1)

    service.embed("um")
    service.embed("dois")
    result = service.embed("um")

    assert result.values == (3.0,)
    assert result.cached is False
    assert len(session.calls) == 3


def test_cache_can_be_disabled() -> None:
    session = FakeSession(
        FakeResponse({"embeddings": [[1.0]]}),
        FakeResponse({"embeddings": [[1.0]]}),
    )
    service = make_service(session, cache_size=0)

    service.embed("texto")
    service.embed("texto")

    assert len(session.calls) == 2
    assert service.cache_info().size == 0


def test_clear_cache_resets_entries_and_metrics() -> None:
    session = FakeSession(FakeResponse({"embeddings": [[1.0]]}))
    service = make_service(session)
    service.embed("texto")
    service.embed("texto")

    service.clear_cache()

    assert service.cache_info().size == 0
    assert service.cache_info().hits == 0
    assert service.cache_info().misses == 0


def test_empty_batch_returns_without_http_request() -> None:
    session = FakeSession()
    service = make_service(session)

    assert service.embed_many([]) == []
    assert session.calls == []


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_blank_text_is_rejected(text: str) -> None:
    service = make_service(FakeSession())

    with pytest.raises(ValueError, match="não pode ser vazio"):
        service.embed(text)


def test_non_string_text_is_rejected() -> None:
    service = make_service(FakeSession())

    with pytest.raises(TypeError, match="deve ser uma string"):
        service.embed(123)  # type: ignore[arg-type]


def test_disabled_service_raises_without_http_request() -> None:
    session = FakeSession()
    service = make_service(session, enabled=False)

    with pytest.raises(EmbeddingUnavailableError, match="desativada"):
        service.embed("texto")

    assert session.calls == []


@pytest.mark.parametrize(
    "error",
    [requests.ConnectionError("offline"), requests.Timeout("demorou")],
)
def test_connection_failures_are_reported_as_unavailable(
    error: Exception,
) -> None:
    service = make_service(FakeSession(error))

    with pytest.raises(EmbeddingUnavailableError, match="não está disponível"):
        service.embed("texto")


def test_http_error_is_reported_as_service_error() -> None:
    response = FakeResponse(
        {"error": "modelo ausente"},
        error=requests.HTTPError("404"),
    )
    service = make_service(FakeSession(response))

    with pytest.raises(EmbeddingServiceError, match="recusou"):
        service.embed("texto")


def test_invalid_json_is_rejected() -> None:
    service = make_service(FakeSession(FakeResponse(invalid_json=True)))

    with pytest.raises(EmbeddingResponseError, match="JSON válido"):
        service.embed("texto")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "objeto JSON"),
        ({}, "lista 'embeddings'"),
        ({"embeddings": []}, "quantidade"),
        ({"embeddings": [[]]}, "lista numérica não vazia"),
        ({"embeddings": [[1.0, "x"]]}, "não é numérico"),
        ({"embeddings": [[1.0, float("nan")]]}, "numérico inválido"),
    ],
)
def test_invalid_payload_is_rejected(payload: Any, message: str) -> None:
    service = make_service(FakeSession(FakeResponse(payload)))

    with pytest.raises(EmbeddingResponseError, match=message):
        service.embed("texto")


def test_mixed_dimensions_in_batch_are_rejected() -> None:
    payload = {"embeddings": [[1.0, 2.0], [3.0]]}
    service = make_service(FakeSession(FakeResponse(payload)))

    with pytest.raises(EmbeddingResponseError, match="dimensões diferentes"):
        service.embed_many(["um", "dois"])


def test_dimension_change_during_session_is_rejected() -> None:
    session = FakeSession(
        FakeResponse({"embeddings": [[1.0, 2.0]]}),
        FakeResponse({"embeddings": [[1.0, 2.0, 3.0]]}),
    )
    service = make_service(session)
    service.embed("primeiro")

    with pytest.raises(EmbeddingResponseError, match="mudou durante"):
        service.embed("segundo")


def test_constructor_validates_configuration() -> None:
    with pytest.raises(ValueError, match="URL"):
        OllamaEmbeddingService(url=" ")

    with pytest.raises(ValueError, match="modelo"):
        OllamaEmbeddingService(model=" ")

    with pytest.raises(ValueError, match="timeout"):
        OllamaEmbeddingService(timeout=0)

    with pytest.raises(ValueError, match="cache"):
        OllamaEmbeddingService(cache_size=-1)


def test_close_closes_injected_session() -> None:
    session = FakeSession()
    service = make_service(session)

    service.close()

    assert session.closed is True
