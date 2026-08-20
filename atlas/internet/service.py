"""Orquestra pesquisa mult fonte atrás da política de conectores."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import time
from typing import Callable
from uuid import uuid4

from atlas.connectors import (
    ConnectorDecision,
    ConnectorGuard,
    ConnectorOperation,
    ConnectorPrincipal,
)
from atlas.internet.models import (
    ProviderStatus,
    ProviderTrace,
    RawSearchResult,
    SearchStatus,
    WebSearchRequest,
    WebSearchResponse,
)
from atlas.internet.provider import (
    SearchProvider,
    SearchProviderError,
    SearchProviderRegistry,
)
from atlas.internet.ranking import rank_results


class WebSearchService:
    """Consulta fontes isoladamente e consolida somente resultados seguros."""

    def __init__(
        self,
        guard: ConnectorGuard,
        providers: tuple[SearchProvider, ...],
        *,
        max_per_domain: int = 2,
        max_workers: int = 4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_per_domain <= 0 or max_workers <= 0:
            raise ValueError("Os limites do serviço devem ser positivos.")

        self._guard = guard
        self._providers = SearchProviderRegistry(providers)
        self._max_per_domain = max_per_domain
        self._max_workers = max_workers
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def search(
        self,
        request: WebSearchRequest,
        principal: ConnectorPrincipal,
    ) -> WebSearchResponse:
        """Pesquisa sem permitir que conteúdo web acione o Atlas."""

        retrieved_at = self._now()
        operation = ConnectorOperation(
            connector_id="web.search",
            capability="query",
            parameters={
                "query_sha256": sha256(
                    request.query.encode("utf-8")
                ).hexdigest(),
                "max_results": request.max_results,
                "safe_search": request.safe_search,
            },
        )
        authorization = self._guard.authorize(operation, principal)

        if not authorization.allowed:
            return WebSearchResponse(
                trace_id=uuid4().hex,
                query=request.query,
                status=SearchStatus.DENIED,
                results=(),
                providers=(),
                retrieved_at=retrieved_at,
                connector_decision=authorization.decision,
                reason=authorization.reason,
            )

        providers = self._providers.all()

        if not providers:
            return WebSearchResponse(
                trace_id=uuid4().hex,
                query=request.query,
                status=SearchStatus.FAILED,
                results=(),
                providers=(),
                retrieved_at=retrieved_at,
                connector_decision=ConnectorDecision.ALLOWED,
                reason="Nenhuma fonte de pesquisa está configurada.",
            )

        per_provider_limit = min(20, max(5, request.max_results * 2))

        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(providers))
        ) as executor:
            futures = {
                provider.provider_id: executor.submit(
                    self._query_provider,
                    provider,
                    request,
                    per_provider_limit,
                )
                for provider in providers
            }

        all_results: list[RawSearchResult] = []
        traces: list[ProviderTrace] = []

        for provider in providers:
            results, trace = futures[provider.provider_id].result()
            all_results.extend(results)
            traces.append(trace)

        failed_count = sum(
            trace.status is ProviderStatus.FAILED for trace in traces
        )

        if failed_count == len(traces):
            status = SearchStatus.FAILED
            reason = "Todas as fontes configuradas falharam."
        elif failed_count:
            status = SearchStatus.PARTIAL
            reason = "A pesquisa foi concluída com fontes indisponíveis."
        else:
            status = SearchStatus.SUCCESS
            reason = "Pesquisa concluída."

        weights = {
            provider.provider_id: provider.trust_weight
            for provider in providers
        }
        ranked = rank_results(
            request.query,
            tuple(all_results),
            provider_weights=weights,
            max_results=request.max_results,
            max_per_domain=self._max_per_domain,
            retrieved_at=retrieved_at,
        )
        return WebSearchResponse(
            trace_id=uuid4().hex,
            query=request.query,
            status=status,
            results=ranked,
            providers=tuple(traces),
            retrieved_at=retrieved_at,
            connector_decision=ConnectorDecision.ALLOWED,
            reason=reason,
        )

    @staticmethod
    def _query_provider(
        provider: SearchProvider,
        request: WebSearchRequest,
        limit: int,
    ) -> tuple[tuple[RawSearchResult, ...], ProviderTrace]:
        started_at = time.perf_counter()

        try:
            results = provider.search(request, limit=limit)
            valid_results = tuple(
                result
                for result in results[:limit]
                if result.provider_id == provider.provider_id
            )
            return valid_results, ProviderTrace(
                provider_id=provider.provider_id,
                status=ProviderStatus.SUCCEEDED,
                result_count=len(valid_results),
                duration_ms=(time.perf_counter() - started_at) * 1000,
            )
        except SearchProviderError as error:
            error_code = error.code
        except Exception:
            error_code = "provider_failure"

        return (), ProviderTrace(
            provider_id=provider.provider_id,
            status=ProviderStatus.FAILED,
            result_count=0,
            duration_ms=(time.perf_counter() - started_at) * 1000,
            error_code=error_code,
        )

    def _now(self) -> datetime:
        now = self._clock()

        if now.tzinfo is None:
            raise ValueError("O relógio da pesquisa deve possuir fuso horário.")

        return now.astimezone(timezone.utc)
