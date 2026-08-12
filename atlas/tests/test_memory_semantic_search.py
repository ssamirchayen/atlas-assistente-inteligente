from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atlas.memory.database import SCHEMA_VERSION, MemoryStore
from atlas.memory.embeddings import (
    EmbeddingUnavailableError,
    EmbeddingVector,
)


class FakeEmbeddingService:
    def __init__(
        self,
        vectors: dict[str, tuple[float, ...]],
        *,
        model: str = "test-embedding",
        failures: int = 0,
    ) -> None:
        self.vectors = vectors
        self.model = model
        self.failures = failures
        self.embed_calls: list[str] = []
        self.batch_calls: list[list[str]] = []
        self.closed = False

    def embed(self, text: str) -> EmbeddingVector:
        self.embed_calls.append(text)
        self._fail_if_requested()
        return self._result(text)

    def embed_many(self, texts: list[str]) -> list[EmbeddingVector]:
        self.batch_calls.append(list(texts))
        self._fail_if_requested()
        return [self._result(text) for text in texts]

    def close(self) -> None:
        self.closed = True

    def _fail_if_requested(self) -> None:
        if self.failures <= 0:
            return

        self.failures -= 1
        raise EmbeddingUnavailableError("Ollama fora do ar")

    def _result(self, text: str) -> EmbeddingVector:
        return EmbeddingVector(
            text=text,
            values=self.vectors[text],
            model=self.model,
        )


def make_memory(
    database_path: Path,
    service: FakeEmbeddingService,
    *,
    minimum_score: float = 0.25,
) -> MemoryStore:
    return MemoryStore(
        database_path,
        embedding_service=service,
        semantic_enabled=True,
        semantic_min_score=minimum_score,
    )


def test_semantic_search_finds_memory_without_equal_words(
    tmp_path: Path,
) -> None:
    relevant = "Ssamir mora em Manaus"
    irrelevant = "O curso começa na segunda-feira"
    query = "Em qual cidade ele vive?"
    service = FakeEmbeddingService(
        {
            query: (1.0, 0.0),
            relevant: (1.0, 0.0),
            irrelevant: (0.0, 1.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        memory.remember_record(relevant)
        memory.remember_record(irrelevant)

        results = memory.search_detailed(query)

    assert [result.record.content for result in results] == [relevant]
    assert results[0].strategy == "hybrid"
    assert results[0].semantic_score == pytest.approx(1.0)
    assert results[0].lexical_score == 0.0


def test_hybrid_ranking_uses_lexical_signal_as_tiebreaker(
    tmp_path: Path,
) -> None:
    query = "curso de radiologia"
    exact = "Ssamir iniciou o curso de radiologia"
    related = "Ssamir estuda diagnóstico por imagem"
    service = FakeEmbeddingService(
        {
            query: (1.0, 0.0),
            exact: (1.0, 0.0),
            related: (1.0, 0.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        memory.remember_record(related)
        memory.remember_record(exact)

        results = memory.search_detailed(query)

    assert [result.record.content for result in results] == [exact, related]
    assert results[0].lexical_score > results[1].lexical_score


def test_hybrid_ranking_uses_importance_when_relevance_ties(
    tmp_path: Path,
) -> None:
    query = "qual é minha preferência?"
    important = "Ssamir prefere respostas objetivas"
    ordinary = "Ssamir prefere café sem açúcar"
    service = FakeEmbeddingService(
        {
            query: (1.0, 0.0),
            important: (1.0, 0.0),
            ordinary: (1.0, 0.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        memory.remember_record(important, importance=0.95)
        memory.remember_record(ordinary, importance=0.10)

        results = memory.search_detailed(query)

    assert results[0].record.content == important
    assert results[0].importance_score == 0.95


def test_embeddings_are_persisted_and_reused_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.db"
    content = "Ssamir está cursando ADS"
    first_query = "O que ele estuda?"
    first_service = FakeEmbeddingService(
        {
            first_query: (1.0, 0.0),
            content: (1.0, 0.0),
        }
    )

    with make_memory(database_path, first_service) as memory:
        memory.remember_record(content)
        assert memory.search(first_query) == [content]

        count = memory.conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings"
        ).fetchone()[0]

    second_query = "Qual faculdade ele faz?"
    second_service = FakeEmbeddingService(
        {second_query: (1.0, 0.0)}
    )

    with make_memory(database_path, second_service) as reopened:
        assert reopened.search(second_query) == [content]

    assert count == 1
    assert second_service.batch_calls == []


def test_content_update_invalidates_and_regenerates_embedding(
    tmp_path: Path,
) -> None:
    original = "Ssamir estuda administração"
    updated = "Ssamir estuda análise de sistemas"
    first_query = "Qual curso?"
    second_query = "O que Ssamir estuda agora?"
    service = FakeEmbeddingService(
        {
            first_query: (1.0, 0.0),
            second_query: (0.0, 1.0),
            original: (1.0, 0.0),
            updated: (0.0, 1.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        record = memory.remember_record(original)
        memory.search(first_query)
        assert memory.conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings"
        ).fetchone()[0] == 1

        memory.update(record.id, content=updated)
        assert memory.conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings"
        ).fetchone()[0] == 0

        assert memory.search(second_query) == [updated]
        assert service.batch_calls[-1] == [updated]


def test_metadata_update_keeps_existing_embedding(tmp_path: Path) -> None:
    content = "Ssamir mora em Manaus"
    query = "Onde ele vive?"
    service = FakeEmbeddingService(
        {
            query: (1.0, 0.0),
            content: (1.0, 0.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        record = memory.remember_record(content)
        memory.search(query)
        memory.update(record.id, importance=0.9)
        memory.search(query)

    assert service.batch_calls == [[content]]


def test_forget_removes_persisted_embedding(tmp_path: Path) -> None:
    content = "Ssamir usa Windows 11"
    query = "Qual sistema operacional?"
    service = FakeEmbeddingService(
        {
            query: (1.0, 0.0),
            content: (1.0, 0.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        record = memory.remember_record(content)
        memory.search(query)
        assert memory.forget(record.id) is True

        count = memory.conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings"
        ).fetchone()[0]

    assert count == 0


def test_ollama_failure_falls_back_and_opens_session_circuit(
    tmp_path: Path,
) -> None:
    content = "Ssamir mora em Manaus"
    query = "Onde Ssamir mora?"
    service = FakeEmbeddingService({}, failures=1)

    with make_memory(tmp_path / "memory.db", service) as memory:
        memory.remember_record(content)

        first = memory.search_detailed(query)
        second = memory.search_detailed(query)

        assert [result.record.content for result in first] == [content]
        assert [result.strategy for result in first] == ["lexical"]
        assert [result.record.content for result in second] == [content]
        assert memory.semantic_last_error == "Ollama fora do ar"

    assert service.embed_calls == [query]


def test_semantic_search_can_retry_after_reset(tmp_path: Path) -> None:
    content = "Ssamir mora em Manaus"
    semantic_query = "Em qual cidade ele vive?"
    lexical_query = "Onde Ssamir mora?"
    service = FakeEmbeddingService(
        {
            semantic_query: (1.0, 0.0),
            content: (1.0, 0.0),
        },
        failures=1,
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        memory.remember_record(content)
        assert memory.search(lexical_query) == [content]

        memory.reset_semantic_search()
        results = memory.search_detailed(semantic_query)

    assert results[0].strategy == "hybrid"
    assert results[0].record.content == content


def test_minimum_score_filters_unrelated_memories(tmp_path: Path) -> None:
    content = "Ssamir gosta de café"
    query = "Qual é a placa do carro?"
    service = FakeEmbeddingService(
        {
            query: (1.0, 0.0),
            content: (0.0, 1.0),
        }
    )

    with make_memory(
        tmp_path / "memory.db",
        service,
        minimum_score=0.30,
    ) as memory:
        memory.remember_record(content, importance=0.1)

        assert memory.search(query) == []


def test_reindex_only_generates_missing_vectors_unless_forced(
    tmp_path: Path,
) -> None:
    first = "Primeira memória"
    second = "Segunda memória"
    service = FakeEmbeddingService(
        {
            first: (1.0, 0.0),
            second: (0.0, 1.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        memory.remember_record(first)
        memory.remember_record(second)

        assert memory.reindex_embeddings() == 2
        assert memory.reindex_embeddings() == 0
        assert memory.reindex_embeddings(force=True) == 2

    assert service.batch_calls == [[second, first], [second, first]]


def test_different_models_keep_independent_persisted_vectors(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.db"
    content = "Memória compartilhada"
    first_service = FakeEmbeddingService(
        {content: (1.0, 0.0)},
        model="model-a",
    )

    with make_memory(database_path, first_service) as memory:
        memory.remember_record(content)
        memory.reindex_embeddings()

    second_service = FakeEmbeddingService(
        {content: (0.0, 1.0)},
        model="model-b",
    )

    with make_memory(database_path, second_service) as reopened:
        reopened.reindex_embeddings()
        models = {
            row[0]
            for row in reopened.conn.execute(
                "SELECT model FROM memory_embeddings"
            ).fetchall()
        }

    assert models == {"model-a", "model-b"}


def test_empty_query_uses_legacy_recent_search_without_embedding(
    tmp_path: Path,
) -> None:
    service = FakeEmbeddingService({})

    with make_memory(tmp_path / "memory.db", service) as memory:
        memory.remember_record("Memória recente")
        results = memory.search_detailed("")

    assert results[0].record.content == "Memória recente"
    assert results[0].strategy == "lexical"
    assert service.embed_calls == []


def test_hybrid_search_keeps_access_audit(tmp_path: Path) -> None:
    content = "Ssamir está criando o Atlas"
    query = "Qual projeto ele desenvolve?"
    service = FakeEmbeddingService(
        {
            query: (1.0, 0.0),
            content: (1.0, 0.0),
        }
    )

    with make_memory(tmp_path / "memory.db", service) as memory:
        created = memory.remember_record(content)
        result = memory.search_records(query)[0]
        persisted = memory.get(created.id)

    assert result.access_count == 1
    assert result.last_accessed_at is not None
    assert persisted is not None
    assert persisted.access_count == 1


def test_schema_v1_is_migrated_to_embedding_table(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            source TEXT NOT NULL DEFAULT 'user',
            importance REAL NOT NULL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_accessed_at TEXT,
            access_count INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.execute("PRAGMA user_version = 1")
    connection.commit()
    connection.close()

    with MemoryStore(database_path, semantic_enabled=False) as memory:
        tables = {
            row[0]
            for row in memory.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version = memory.conn.execute("PRAGMA user_version").fetchone()[0]
        backup = memory.migration_backup

    assert "memory_embeddings" in tables
    assert version == SCHEMA_VERSION
    assert backup is not None
    assert backup.is_file()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"semantic_min_score": -0.1}, "entre 0 e 1"),
        ({"semantic_min_score": 1.1}, "entre 0 e 1"),
        ({"semantic_candidate_limit": 0}, "maior que zero"),
    ],
)
def test_semantic_configuration_is_validated(
    tmp_path: Path,
    kwargs: dict[str, float | int],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        MemoryStore(tmp_path / "memory.db", **kwargs)
