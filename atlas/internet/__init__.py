"""Pesquisa web mult fonte, rastreável e protegida por conectores."""

from atlas.internet.factory import (
    build_default_search_providers,
    build_default_web_search_service,
    build_local_search_principal,
)
from atlas.internet.models import (
    ProviderStatus,
    ProviderTrace,
    RawSearchResult,
    SearchFreshness,
    SearchResult,
    SearchStatus,
    WebSearchRequest,
    WebSearchResponse,
)
from atlas.internet.provider import (
    SearchProvider,
    SearchProviderError,
    SearchProviderRegistry,
)
from atlas.internet.providers import (
    BraveSearchProvider,
    SearxngSearchProvider,
    WikipediaSearchProvider,
)
from atlas.internet.service import WebSearchService

__all__ = [
    "BraveSearchProvider",
    "ProviderStatus",
    "ProviderTrace",
    "RawSearchResult",
    "SearchFreshness",
    "SearchProvider",
    "SearchProviderError",
    "SearchProviderRegistry",
    "SearchResult",
    "SearchStatus",
    "SearxngSearchProvider",
    "WebSearchRequest",
    "WebSearchResponse",
    "WebSearchService",
    "WikipediaSearchProvider",
    "build_default_search_providers",
    "build_default_web_search_service",
    "build_local_search_principal",
]
