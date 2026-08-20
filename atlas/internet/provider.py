"""Contrato e catálogo de provedores de pesquisa."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from atlas.internet.models import RawSearchResult, WebSearchRequest


class SearchProviderError(RuntimeError):
    """Falha sanitizada que pode aparecer na rastreabilidade."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip().lower() or "provider_failure"


@runtime_checkable
class SearchProvider(Protocol):
    """Contrato mínimo de uma fonte de resultados."""

    provider_id: str
    display_name: str
    trust_weight: float

    def search(
        self,
        request: WebSearchRequest,
        *,
        limit: int,
    ) -> tuple[RawSearchResult, ...]: ...


class SearchProviderRegistry:
    """Mantém fontes únicas e em ordem determinística."""

    def __init__(
        self,
        providers: Iterable[SearchProvider] | None = None,
    ) -> None:
        self._providers: dict[str, SearchProvider] = {}

        for provider in providers or ():
            self.register(provider)

    def register(self, provider: SearchProvider) -> None:
        if not isinstance(provider, SearchProvider):
            raise TypeError("O provedor não implementa SearchProvider.")

        provider_id = provider.provider_id.strip().lower()

        if not provider_id:
            raise ValueError("O identificador do provedor é obrigatório.")

        if not 0.0 <= provider.trust_weight <= 1.0:
            raise ValueError("O peso de confiança deve ficar entre 0 e 1.")

        if provider_id in self._providers:
            raise ValueError(
                f"Já existe um provedor registrado como '{provider_id}'."
            )

        self._providers[provider_id] = provider

    def all(self) -> tuple[SearchProvider, ...]:
        return tuple(self._providers.values())

    def get(self, provider_id: str) -> SearchProvider | None:
        return self._providers.get(provider_id.strip().lower())
