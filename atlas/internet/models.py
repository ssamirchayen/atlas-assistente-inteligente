"""Contratos públicos da pesquisa rastreável na internet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re

from atlas.connectors.models import ConnectorDecision


class SearchFreshness(StrEnum):
    """Janela temporal solicitada aos provedores compatíveis."""

    ANY = "any"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class SearchStatus(StrEnum):
    """Estado consolidado de uma pesquisa mult fonte."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    DENIED = "denied"


class ProviderStatus(StrEnum):
    """Estado seguro de uma consulta individual."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WebSearchRequest:
    """Consulta normalizada antes de sair do processo do Atlas."""

    query: str
    max_results: int = 5
    language: str = "pt-BR"
    country: str = "BR"
    freshness: SearchFreshness = SearchFreshness.ANY
    safe_search: bool = True

    def __post_init__(self) -> None:
        query = " ".join(self.query.split())
        language = self.language.strip()
        country = self.country.strip().upper()

        if len(query) < 2:
            raise ValueError("A pesquisa deve possuir ao menos 2 caracteres.")

        if len(query) > 500:
            raise ValueError("A pesquisa deve possuir no máximo 500 caracteres.")

        if not 1 <= self.max_results <= 20:
            raise ValueError("O total de resultados deve ficar entre 1 e 20.")

        if not re.fullmatch(r"[a-zA-Z]{2}(?:-[a-zA-Z]{2})?", language):
            raise ValueError("O idioma deve usar o formato pt ou pt-BR.")

        if not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("O país deve usar um código ISO de duas letras.")

        if not isinstance(self.freshness, SearchFreshness):
            raise TypeError("freshness deve ser um SearchFreshness.")

        object.__setattr__(self, "query", query)
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "country", country)


@dataclass(frozen=True, slots=True)
class RawSearchResult:
    """Resultado ainda não deduplicado nem classificado."""

    provider_id: str
    title: str
    url: str
    snippet: str
    source_name: str
    provider_rank: int
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        provider_id = self.provider_id.strip().lower()
        title = " ".join(self.title.split())
        url = self.url.strip()
        snippet = " ".join(self.snippet.split())
        source_name = " ".join(self.source_name.split())

        if not provider_id:
            raise ValueError("O provedor do resultado é obrigatório.")

        if not title or not url:
            raise ValueError("Título e URL do resultado são obrigatórios.")

        if self.provider_rank <= 0:
            raise ValueError("A posição do provedor deve ser positiva.")

        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "snippet", snippet[:1000])
        object.__setattr__(self, "source_name", source_name or provider_id)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Resultado final com citação, pontuação e origem preservadas."""

    citation_id: int
    title: str
    url: str
    domain: str
    snippet: str
    source_name: str
    provider_ids: tuple[str, ...]
    provider_rank: int
    score: float
    retrieved_at: datetime
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderTrace:
    """Evidência operacional sem resposta bruta ou credenciais."""

    provider_id: str
    status: ProviderStatus
    result_count: int
    duration_ms: float
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class WebSearchResponse:
    """Resposta consolidada e adequada para GUI, API ou terminal."""

    trace_id: str
    query: str
    status: SearchStatus
    results: tuple[SearchResult, ...]
    providers: tuple[ProviderTrace, ...]
    retrieved_at: datetime
    connector_decision: ConnectorDecision
    reason: str

    @property
    def succeeded(self) -> bool:
        return self.status in {SearchStatus.SUCCESS, SearchStatus.PARTIAL}

    def format_message(self) -> str:
        """Formata citações legíveis sem ocultar a origem do conteúdo."""

        if self.status is SearchStatus.DENIED:
            return f"Pesquisa bloqueada: {self.reason}"

        if not self.results:
            if self.status is SearchStatus.FAILED:
                return "Não foi possível consultar as fontes configuradas."
            return "Não encontrei resultados nas fontes consultadas."

        lines = [
            f"Encontrei {len(self.results)} resultado(s) com fontes:",
        ]

        for result in self.results:
            lines.append(
                f"[{result.citation_id}] {result.title} — {result.domain}"
            )

            if result.snippet:
                lines.append(result.snippet[:280])

            lines.append(result.url)

        if self.status is SearchStatus.PARTIAL:
            lines.append("Algumas fontes não responderam nesta pesquisa.")

        return "\n".join(lines)
