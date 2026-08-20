"""Adaptadores de pesquisa para Wikipédia, Brave e SearXNG."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import urlsplit

from atlas.internet.http import JsonHttpClient
from atlas.internet.models import (
    RawSearchResult,
    SearchFreshness,
    WebSearchRequest,
)
class WikipediaSearchProvider:
    """Pesquisa artigos usando a Action API da Wikipédia em português."""

    provider_id = "wikipedia.pt"
    display_name = "Wikipédia em português"
    trust_weight = 0.82
    _ENDPOINT = "https://pt.wikipedia.org/w/api.php"

    def __init__(self, client: JsonHttpClient, *, timeout: float = 8.0) -> None:
        self._client = client
        self._timeout = timeout

    def search(
        self,
        request: WebSearchRequest,
        *,
        limit: int,
    ) -> tuple[RawSearchResult, ...]:
        payload = self._client.get_json(
            self._ENDPOINT,
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": request.query,
                "gsrlimit": min(limit, 20),
                "prop": "extracts|info",
                "exintro": 1,
                "explaintext": 1,
                "exsentences": 3,
                "inprop": "url",
                "format": "json",
                "formatversion": 2,
            },
            timeout=self._timeout,
        )
        query = payload.get("query")

        if not isinstance(query, Mapping):
            return ()

        pages = query.get("pages")

        if not isinstance(pages, list):
            return ()

        results: list[RawSearchResult] = []

        for page in pages:
            if not isinstance(page, Mapping):
                continue

            title = _text(page.get("title"))
            url = _text(page.get("fullurl"))
            extract = _text(page.get("extract"))

            if not title or not url:
                continue

            results.append(
                RawSearchResult(
                    provider_id=self.provider_id,
                    title=title,
                    url=url,
                    snippet=extract,
                    source_name="Wikipédia",
                    provider_rank=len(results) + 1,
                )
            )

            if len(results) >= limit:
                break

        return tuple(results)


class BraveSearchProvider:
    """Pesquisa a web pelo endpoint oficial do Brave Search."""

    provider_id = "brave.web"
    display_name = "Brave Search"
    trust_weight = 0.88
    _ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    _FRESHNESS = {
        SearchFreshness.DAY: "pd",
        SearchFreshness.WEEK: "pw",
        SearchFreshness.MONTH: "pm",
        SearchFreshness.YEAR: "py",
    }

    def __init__(
        self,
        client: JsonHttpClient,
        *,
        api_key: str,
        timeout: float = 8.0,
    ) -> None:
        api_key = api_key.strip()

        if not api_key:
            raise ValueError("A chave do Brave Search é obrigatória.")

        self._client = client
        self._api_key = api_key
        self._timeout = timeout

    def search(
        self,
        request: WebSearchRequest,
        *,
        limit: int,
    ) -> tuple[RawSearchResult, ...]:
        params: dict[str, object] = {
            "q": request.query,
            "count": min(limit, 20),
            "country": request.country.lower(),
            "search_lang": request.language.split("-", 1)[0].lower(),
            "safesearch": "strict" if request.safe_search else "off",
        }
        freshness = self._FRESHNESS.get(request.freshness)

        if freshness:
            params["freshness"] = freshness

        payload = self._client.get_json(
            self._ENDPOINT,
            params=params,
            headers={"X-Subscription-Token": self._api_key},
            timeout=self._timeout,
        )
        web = payload.get("web")

        if not isinstance(web, Mapping):
            return ()

        raw_results = web.get("results")

        if not isinstance(raw_results, list):
            return ()

        results: list[RawSearchResult] = []

        for item in raw_results:
            if not isinstance(item, Mapping):
                continue

            title = _text(item.get("title"))
            url = _text(item.get("url"))

            if not title or not url:
                continue

            profile = item.get("profile")
            source_name = (
                _text(profile.get("long_name"))
                if isinstance(profile, Mapping)
                else ""
            )
            results.append(
                RawSearchResult(
                    provider_id=self.provider_id,
                    title=title,
                    url=url,
                    snippet=_text(item.get("description")),
                    source_name=source_name or _domain(url) or "Web",
                    provider_rank=len(results) + 1,
                    published_at=_parse_datetime(item.get("page_age")),
                )
            )

            if len(results) >= limit:
                break

        return tuple(results)


class SearxngSearchProvider:
    """Usa uma instância SearXNG configurada pelo operador."""

    provider_id = "searxng.web"
    display_name = "SearXNG"
    trust_weight = 0.72

    def __init__(
        self,
        client: JsonHttpClient,
        *,
        base_url: str,
        timeout: float = 8.0,
        allow_private_endpoint: bool = False,
    ) -> None:
        self._endpoint = _validate_searxng_url(
            base_url,
            allow_private_endpoint=allow_private_endpoint,
        )
        self._client = client
        self._timeout = timeout

    def search(
        self,
        request: WebSearchRequest,
        *,
        limit: int,
    ) -> tuple[RawSearchResult, ...]:
        params: dict[str, object] = {
            "q": request.query,
            "format": "json",
            "language": request.language,
            "safesearch": 1 if request.safe_search else 0,
        }

        if request.freshness is not SearchFreshness.ANY:
            params["time_range"] = request.freshness.value

        payload = self._client.get_json(
            self._endpoint,
            params=params,
            timeout=self._timeout,
        )
        raw_results = payload.get("results")

        if not isinstance(raw_results, list):
            return ()

        results: list[RawSearchResult] = []

        for item in raw_results:
            if not isinstance(item, Mapping):
                continue

            title = _text(item.get("title"))
            url = _text(item.get("url"))

            if not title or not url:
                continue

            engines = item.get("engines")
            source_name = (
                ", ".join(str(engine) for engine in engines[:3])
                if isinstance(engines, list)
                else _text(item.get("engine"))
            )
            results.append(
                RawSearchResult(
                    provider_id=self.provider_id,
                    title=title,
                    url=url,
                    snippet=_text(item.get("content")),
                    source_name=source_name or _domain(url) or "Web",
                    provider_rank=len(results) + 1,
                    published_at=_parse_datetime(item.get("publishedDate")),
                )
            )

            if len(results) >= limit:
                break

        return tuple(results)


def _validate_searxng_url(
    base_url: str,
    *,
    allow_private_endpoint: bool,
) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A URL do SearXNG deve usar HTTP ou HTTPS.")

    hostname = parsed.hostname.casefold()
    is_loopback_name = hostname in {"localhost", "127.0.0.1", "::1"}
    is_private = is_loopback_name

    try:
        address = ip_address(hostname)
        is_private = (
            address.is_private
            or address.is_loopback
            or address.is_link_local
        )
    except ValueError:
        pass

    private_http_allowed = is_private and allow_private_endpoint

    if parsed.scheme != "https" and not (
        is_loopback_name or private_http_allowed
    ):
        raise ValueError("SearXNG remoto exige HTTPS.")

    if is_private and not (allow_private_endpoint or is_loopback_name):
        raise ValueError("Endpoint privado exige autorização explícita.")

    if parsed.path.rstrip("/").endswith("/search"):
        return normalized

    return f"{normalized}/search"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold()


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
