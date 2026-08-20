from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from atlas.connectors import (
    ConnectorCapability,
    ConnectorDecision,
    ConnectorGuard,
    ConnectorManifest,
    ConnectorPrincipal,
    ConnectorRegistry,
    ConnectorRisk,
)
from atlas.internet.models import (
    ProviderStatus,
    RawSearchResult,
    SearchStatus,
    WebSearchRequest,
)
from atlas.internet.provider import SearchProviderError
from atlas.internet.ranking import canonicalize_public_url, rank_results
from atlas.internet.service import WebSearchService


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


@dataclass
class StubProvider:
    provider_id: str
    results: tuple[RawSearchResult, ...] = ()
    error: SearchProviderError | None = None
    display_name: str = "Stub"
    trust_weight: float = 0.7
    calls: list[WebSearchRequest] = field(default_factory=list)

    def search(
        self,
        request: WebSearchRequest,
        *,
        limit: int,
    ) -> tuple[RawSearchResult, ...]:
        self.calls.append(request)

        if self.error:
            raise self.error

        return self.results[:limit]


def make_guard() -> ConnectorGuard:
    manifest = ConnectorManifest(
        connector_id="web.search",
        display_name="Pesquisa web",
        description="Pesquisa somente leitura.",
        capabilities=(
            ConnectorCapability(
                name="query",
                required_scope="internet:search",
                risk=ConnectorRisk.READ_ONLY,
            ),
        ),
        operations_per_minute=30,
    )
    return ConnectorGuard(ConnectorRegistry((manifest,)))


def principal(*scopes: str) -> ConnectorPrincipal:
    return ConnectorPrincipal(
        principal_id="ssamir",
        role="local_operator",
        scopes=frozenset(scopes),
    )


def raw(
    provider_id: str,
    title: str,
    url: str,
    *,
    rank: int = 1,
    snippet: str = "Atlas assistente empresarial local.",
) -> RawSearchResult:
    return RawSearchResult(
        provider_id=provider_id,
        title=title,
        url=url,
        snippet=snippet,
        source_name="Fonte",
        provider_rank=rank,
    )


def test_service_denies_search_without_scope_before_calling_providers() -> None:
    provider = StubProvider("source.one")
    service = WebSearchService(make_guard(), (provider,), clock=lambda: NOW)

    response = service.search(WebSearchRequest("Atlas"), principal())

    assert response.status is SearchStatus.DENIED
    assert response.connector_decision is ConnectorDecision.DENIED
    assert provider.calls == []


def test_service_isolates_provider_failure_and_returns_partial_results() -> None:
    working = StubProvider(
        "source.one",
        results=(
            raw(
                "source.one",
                "Atlas empresarial",
                "https://example.com/atlas?utm_source=test",
            ),
        ),
    )
    broken = StubProvider(
        "source.two",
        error=SearchProviderError("provider_timeout", "timeout"),
    )
    service = WebSearchService(
        make_guard(),
        (working, broken),
        clock=lambda: NOW,
    )

    response = service.search(
        WebSearchRequest("Atlas empresarial"),
        principal("internet:search"),
    )

    assert response.status is SearchStatus.PARTIAL
    assert len(response.results) == 1
    assert response.results[0].citation_id == 1
    assert response.results[0].url == "https://example.com/atlas"
    assert response.providers[0].status is ProviderStatus.SUCCEEDED
    assert response.providers[1].error_code == "provider_timeout"
    assert "Algumas fontes" in response.format_message()


def test_service_reports_failure_without_leaking_exception() -> None:
    provider = StubProvider(
        "source.one",
        error=SearchProviderError("provider_http_503", "raw secret"),
    )
    service = WebSearchService(make_guard(), (provider,), clock=lambda: NOW)

    response = service.search(
        WebSearchRequest("Atlas"),
        principal("internet:search"),
    )

    assert response.status is SearchStatus.FAILED
    assert response.providers[0].error_code == "provider_http_503"
    assert "raw secret" not in repr(response)


def test_service_without_providers_fails_safely() -> None:
    service = WebSearchService(make_guard(), (), clock=lambda: NOW)

    response = service.search(
        WebSearchRequest("Atlas"),
        principal("internet:search"),
    )

    assert response.status is SearchStatus.FAILED
    assert response.providers == ()
    assert "Nenhuma fonte" in response.reason


def test_service_discards_result_claiming_another_provider_identity() -> None:
    provider = StubProvider(
        "source.one",
        results=(
            raw(
                "spoofed.source",
                "Resultado inválido",
                "https://example.com/spoofed",
            ),
        ),
    )
    service = WebSearchService(make_guard(), (provider,), clock=lambda: NOW)

    response = service.search(
        WebSearchRequest("resultado"),
        principal("internet:search"),
    )

    assert response.status is SearchStatus.SUCCESS
    assert response.results == ()
    assert response.providers[0].result_count == 0


def test_ranking_deduplicates_corroborated_urls() -> None:
    results = rank_results(
        "Atlas assistente",
        (
            raw(
                "source.one",
                "Atlas assistente",
                "https://example.com/atlas?utm_campaign=one",
                rank=2,
            ),
            raw(
                "source.two",
                "Atlas",
                "https://example.com/atlas",
                rank=1,
                snippet="Resumo mais detalhado sobre o Atlas assistente.",
            ),
        ),
        provider_weights={"source.one": 0.5, "source.two": 0.9},
        max_results=5,
        max_per_domain=2,
        retrieved_at=NOW,
    )

    assert len(results) == 1
    assert results[0].provider_ids == ("source.one", "source.two")
    assert results[0].provider_rank == 1
    assert "mais detalhado" in results[0].snippet


def test_ranking_enforces_domain_diversity() -> None:
    raw_results = tuple(
        raw(
            "source.one",
            f"Atlas resultado {index}",
            f"https://dominante.example/page-{index}",
            rank=index,
        )
        for index in range(1, 4)
    ) + (
        raw(
            "source.one",
            "Atlas fonte diversa",
            "https://diversa.example/atlas",
            rank=4,
        ),
    )

    results = rank_results(
        "Atlas",
        raw_results,
        provider_weights={"source.one": 0.7},
        max_results=4,
        max_per_domain=2,
        retrieved_at=NOW,
    )

    assert [result.domain for result in results].count(
        "dominante.example"
    ) == 2
    assert "diversa.example" in {result.domain for result in results}


def test_url_policy_blocks_local_credentials_and_non_http_schemes() -> None:
    assert canonicalize_public_url("http://127.0.0.1/private") is None
    assert canonicalize_public_url("http://localhost/private") is None
    assert canonicalize_public_url("https://user:pass@example.com") is None
    assert canonicalize_public_url("javascript:alert(1)") is None
    assert canonicalize_public_url("https://example.com/") == (
        "https://example.com/"
    )
