from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from atlas.core.config import (
    EMBEDDINGS_ENABLED,
    OLLAMA_EMBEDDING_CACHE_SIZE,
    OLLAMA_EMBEDDING_MODEL,
    OLLAMA_EMBEDDING_TIMEOUT,
    OLLAMA_EMBEDDING_URL,
)


class EmbeddingServiceError(RuntimeError):
    """Erro base do serviço de embeddings do Atlas."""


class EmbeddingUnavailableError(EmbeddingServiceError):
    """O serviço local não está disponível no momento."""


class EmbeddingResponseError(EmbeddingServiceError):
    """O serviço respondeu, mas o conteúdo recebido é inválido."""


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """Vetor imutável gerado para um texto."""

    text: str
    values: tuple[float, ...]
    model: str
    cached: bool = False

    @property
    def dimensions(self) -> int:
        return len(self.values)


@dataclass(frozen=True, slots=True)
class EmbeddingCacheInfo:
    """Snapshot das métricas do cache local em memória."""

    size: int
    max_size: int
    hits: int
    misses: int
    dimensions: int | None


class OllamaEmbeddingService:
    """Gera embeddings locais pelo Ollama com validação e cache LRU."""

    def __init__(
        self,
        *,
        url: str = OLLAMA_EMBEDDING_URL,
        model: str = OLLAMA_EMBEDDING_MODEL,
        timeout: float = OLLAMA_EMBEDDING_TIMEOUT,
        cache_size: int = OLLAMA_EMBEDDING_CACHE_SIZE,
        enabled: bool = EMBEDDINGS_ENABLED,
        session: requests.Session | None = None,
    ) -> None:
        normalized_url = url.strip()
        normalized_model = model.strip()

        if not normalized_url:
            raise ValueError("A URL do serviço de embeddings não pode ser vazia.")

        if not normalized_model:
            raise ValueError("O modelo de embeddings não pode ser vazio.")

        if timeout <= 0:
            raise ValueError("O timeout de embeddings deve ser maior que zero.")

        if cache_size < 0:
            raise ValueError("O tamanho do cache não pode ser negativo.")

        self.url = normalized_url
        self.model = normalized_model
        self.timeout = float(timeout)
        self.cache_size = int(cache_size)
        self.enabled = bool(enabled)
        self._session = session or requests.Session()
        self._cache: OrderedDict[str, tuple[float, ...]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._dimensions: int | None = None

    def embed(self, text: str) -> EmbeddingVector:
        """Gera um vetor para um único texto."""

        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> list[EmbeddingVector]:
        """Gera vetores em lote, preservando a ordem e duplicidades."""

        normalized_texts = [self._normalize_text(text) for text in texts]

        if not normalized_texts:
            return []

        self._ensure_enabled()
        cached: dict[str, tuple[float, ...]] = {}
        missing: list[str] = []

        for text in dict.fromkeys(normalized_texts):
            vector = self._get_cached(text)

            if vector is None:
                missing.append(text)
            else:
                cached[text] = vector

        generated = self._request_embeddings(missing) if missing else {}

        for text, vector in generated.items():
            self._store_cached(text, vector)

        return [
            EmbeddingVector(
                text=text,
                values=cached.get(text) or generated[text],
                model=self.model,
                cached=text in cached,
            )
            for text in normalized_texts
        ]

    def cache_info(self) -> EmbeddingCacheInfo:
        with self._lock:
            return EmbeddingCacheInfo(
                size=len(self._cache),
                max_size=self.cache_size,
                hits=self._hits,
                misses=self._misses,
                dimensions=self._dimensions,
            )

    def clear_cache(self, *, reset_metrics: bool = True) -> None:
        with self._lock:
            self._cache.clear()

            if reset_metrics:
                self._hits = 0
                self._misses = 0

    def close(self) -> None:
        close = getattr(self._session, "close", None)

        if callable(close):
            close()

    def _ensure_enabled(self) -> None:
        if not self.enabled:
            raise EmbeddingUnavailableError(
                "A geração de embeddings está desativada na configuração."
            )

    @staticmethod
    def _normalize_text(text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("O texto do embedding deve ser uma string.")

        normalized = " ".join(text.split())

        if not normalized:
            raise ValueError("O texto do embedding não pode ser vazio.")

        return normalized

    def _get_cached(self, text: str) -> tuple[float, ...] | None:
        with self._lock:
            vector = self._cache.get(text)

            if vector is None:
                self._misses += 1
                return None

            self._cache.move_to_end(text)
            self._hits += 1
            return vector

    def _store_cached(self, text: str, vector: tuple[float, ...]) -> None:
        if self.cache_size == 0:
            return

        with self._lock:
            self._cache[text] = vector
            self._cache.move_to_end(text)

            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    def _request_embeddings(
        self,
        texts: list[str],
    ) -> dict[str, tuple[float, ...]]:
        try:
            response = self._session.post(
                self.url,
                json={
                    "model": self.model,
                    "input": texts,
                    "truncate": True,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except (requests.ConnectionError, requests.Timeout) as error:
            raise EmbeddingUnavailableError(
                "O Ollama não está disponível para gerar embeddings."
            ) from error
        except requests.RequestException as error:
            raise EmbeddingServiceError(
                "O Ollama recusou a solicitação de embeddings."
            ) from error

        try:
            payload = response.json()
        except (ValueError, TypeError) as error:
            raise EmbeddingResponseError(
                "O Ollama retornou uma resposta que não é JSON válido."
            ) from error

        vectors = self._validate_payload(payload, expected_count=len(texts))
        return dict(zip(texts, vectors, strict=True))

    def _validate_payload(
        self,
        payload: Any,
        *,
        expected_count: int,
    ) -> list[tuple[float, ...]]:
        if not isinstance(payload, dict):
            raise EmbeddingResponseError(
                "A resposta de embeddings deve ser um objeto JSON."
            )

        raw_vectors = payload.get("embeddings")

        if not isinstance(raw_vectors, list):
            raise EmbeddingResponseError(
                "A resposta não contém a lista 'embeddings'."
            )

        if len(raw_vectors) != expected_count:
            raise EmbeddingResponseError(
                "A quantidade de embeddings difere da quantidade de textos."
            )

        vectors = [self._validate_vector(vector) for vector in raw_vectors]
        dimensions = len(vectors[0])

        if any(len(vector) != dimensions for vector in vectors):
            raise EmbeddingResponseError(
                "Os embeddings retornados possuem dimensões diferentes."
            )

        with self._lock:
            if self._dimensions is not None and self._dimensions != dimensions:
                raise EmbeddingResponseError(
                    "A dimensão dos embeddings mudou durante a sessão."
                )

            self._dimensions = dimensions

        return vectors

    @staticmethod
    def _validate_vector(vector: Any) -> tuple[float, ...]:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingResponseError(
                "Cada embedding deve ser uma lista numérica não vazia."
            )

        values: list[float] = []

        for item in vector:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise EmbeddingResponseError(
                    "O embedding contém um valor que não é numérico."
                )

            value = float(item)

            if not math.isfinite(value):
                raise EmbeddingResponseError(
                    "O embedding contém um valor numérico inválido."
                )

            values.append(value)

        return tuple(values)
