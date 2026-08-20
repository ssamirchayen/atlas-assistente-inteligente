"""Deduplicação, diversidade e ranking determinístico de resultados."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from ipaddress import ip_address
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from atlas.internet.models import RawSearchResult, SearchResult


_TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref_src",
    }
)


@dataclass(slots=True)
class _Candidate:
    title: str
    url: str
    domain: str
    snippet: str
    source_name: str
    provider_rank: int
    published_at: datetime | None
    provider_ids: set[str] = field(default_factory=set)
    provider_weights: list[float] = field(default_factory=list)


def rank_results(
    query: str,
    raw_results: tuple[RawSearchResult, ...],
    *,
    provider_weights: dict[str, float],
    max_results: int,
    max_per_domain: int,
    retrieved_at: datetime,
) -> tuple[SearchResult, ...]:
    """Combina fontes sem permitir que um domínio monopolize a resposta."""

    if max_results <= 0 or max_per_domain <= 0:
        raise ValueError("Os limites do ranking devem ser positivos.")

    candidates: dict[str, _Candidate] = {}

    for raw in raw_results:
        normalized_url = canonicalize_public_url(raw.url)

        if normalized_url is None:
            continue

        domain = (urlsplit(normalized_url).hostname or "").casefold()
        candidate = candidates.get(normalized_url)
        weight = provider_weights.get(raw.provider_id, 0.5)

        if candidate is None:
            candidates[normalized_url] = _Candidate(
                title=raw.title,
                url=normalized_url,
                domain=domain,
                snippet=raw.snippet,
                source_name=raw.source_name,
                provider_rank=raw.provider_rank,
                published_at=raw.published_at,
                provider_ids={raw.provider_id},
                provider_weights=[weight],
            )
            continue

        candidate.provider_ids.add(raw.provider_id)
        candidate.provider_weights.append(weight)
        candidate.provider_rank = min(
            candidate.provider_rank,
            raw.provider_rank,
        )

        if len(raw.snippet) > len(candidate.snippet):
            candidate.snippet = raw.snippet
            candidate.source_name = raw.source_name

        if raw.published_at and (
            candidate.published_at is None
            or raw.published_at > candidate.published_at
        ):
            candidate.published_at = raw.published_at

    query_tokens = _tokens(query)
    scored: list[tuple[float, _Candidate]] = []

    for candidate in candidates.values():
        content_tokens = _tokens(
            f"{candidate.title} {candidate.snippet}"
        )
        overlap = (
            len(query_tokens & content_tokens) / len(query_tokens)
            if query_tokens
            else 0.0
        )
        position = 1.0 / candidate.provider_rank
        trust = sum(candidate.provider_weights) / len(
            candidate.provider_weights
        )
        corroboration = min(
            1.0,
            max(0, len(candidate.provider_ids) - 1) / 2,
        )
        score = round(
            (overlap * 0.55)
            + (position * 0.25)
            + (trust * 0.15)
            + (corroboration * 0.05),
            6,
        )
        scored.append((score, candidate))

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].provider_rank,
            item[1].title.casefold(),
        )
    )
    domain_counts: Counter[str] = Counter()
    selected: list[tuple[float, _Candidate]] = []

    for score, candidate in scored:
        if domain_counts[candidate.domain] >= max_per_domain:
            continue

        selected.append((score, candidate))
        domain_counts[candidate.domain] += 1

        if len(selected) >= max_results:
            break

    return tuple(
        SearchResult(
            citation_id=index,
            title=candidate.title,
            url=candidate.url,
            domain=candidate.domain,
            snippet=candidate.snippet,
            source_name=candidate.source_name,
            provider_ids=tuple(sorted(candidate.provider_ids)),
            provider_rank=candidate.provider_rank,
            score=score,
            retrieved_at=retrieved_at,
            published_at=candidate.published_at,
        )
        for index, (score, candidate) in enumerate(selected, start=1)
    )


def canonicalize_public_url(url: str) -> str | None:
    """Aceita apenas URLs web públicas e remove rastreadores conhecidos."""

    parsed = urlsplit(url.strip())

    if parsed.scheme not in {"http", "https"}:
        return None

    if not parsed.hostname or parsed.username or parsed.password:
        return None

    hostname = parsed.hostname.casefold().rstrip(".")

    if hostname == "localhost" or hostname.endswith(".local"):
        return None

    try:
        address = ip_address(hostname)

        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
        ):
            return None
    except ValueError:
        pass

    port = parsed.port
    netloc = hostname

    if port and not (
        (parsed.scheme == "http" and port == 80)
        or (parsed.scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"

    query = [
        (key, value)
        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
        if key.casefold() not in _TRACKING_PARAMETERS
        and not key.casefold().startswith("utm_")
    ]
    path = parsed.path or "/"

    if path != "/":
        path = path.rstrip("/")

    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            path,
            urlencode(sorted(query)),
            "",
        )
    )


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return {
        token
        for token in re.findall(r"[a-z0-9]{2,}", without_accents)
    }
