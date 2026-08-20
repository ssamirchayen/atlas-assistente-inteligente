"""Composição padrão da pesquisa web do Atlas."""

from __future__ import annotations

from atlas.connectors import (
    ConnectorCapability,
    ConnectorGuard,
    ConnectorManifest,
    ConnectorPrincipal,
    ConnectorRegistry,
    ConnectorRisk,
)
from atlas.core.config import (
    BRAVE_SEARCH_API_KEY,
    INTERNET_SEARCH_ENABLED,
    INTERNET_SEARCH_MAX_PER_DOMAIN,
    INTERNET_SEARCH_RATE_LIMIT,
    INTERNET_SEARCH_TIMEOUT,
    SEARXNG_ALLOW_PRIVATE,
    SEARXNG_URL,
    USER_NAME,
)
from atlas.internet.http import JsonHttpClient, RequestsJsonClient
from atlas.internet.provider import SearchProvider
from atlas.internet.providers import (
    BraveSearchProvider,
    SearxngSearchProvider,
    WikipediaSearchProvider,
)
from atlas.internet.service import WebSearchService


def build_default_search_providers(
    client: JsonHttpClient | None = None,
) -> tuple[SearchProvider, ...]:
    """Ativa fontes opcionais somente quando sua configuração existe."""

    http_client = client or RequestsJsonClient()

    if not INTERNET_SEARCH_ENABLED:
        return ()

    providers: list[SearchProvider] = [
        WikipediaSearchProvider(
            http_client,
            timeout=INTERNET_SEARCH_TIMEOUT,
        )
    ]

    if BRAVE_SEARCH_API_KEY:
        providers.append(
            BraveSearchProvider(
                http_client,
                api_key=BRAVE_SEARCH_API_KEY,
                timeout=INTERNET_SEARCH_TIMEOUT,
            )
        )

    if SEARXNG_URL:
        providers.append(
            SearxngSearchProvider(
                http_client,
                base_url=SEARXNG_URL,
                timeout=INTERNET_SEARCH_TIMEOUT,
                allow_private_endpoint=SEARXNG_ALLOW_PRIVATE,
            )
        )

    return tuple(providers)


def build_default_web_search_service(
    *,
    providers: tuple[SearchProvider, ...] | None = None,
) -> WebSearchService:
    """Cria a política e o agregador usados pelo núcleo local."""

    manifest = ConnectorManifest(
        connector_id="web.search",
        display_name="Pesquisa web",
        description="Consulta fontes públicas sem executar seu conteúdo.",
        capabilities=(
            ConnectorCapability(
                name="query",
                required_scope="internet:search",
                risk=ConnectorRisk.READ_ONLY,
            ),
        ),
        max_batch_size=1,
        operations_per_minute=INTERNET_SEARCH_RATE_LIMIT,
    )
    guard = ConnectorGuard(ConnectorRegistry((manifest,)))
    return WebSearchService(
        guard,
        providers if providers is not None else build_default_search_providers(),
        max_per_domain=INTERNET_SEARCH_MAX_PER_DOMAIN,
    )


def build_local_search_principal() -> ConnectorPrincipal:
    """Identidade local mínima; não concede escrita externa."""

    return ConnectorPrincipal(
        principal_id=USER_NAME,
        role="local_operator",
        scopes=frozenset({"internet:search"}),
    )
