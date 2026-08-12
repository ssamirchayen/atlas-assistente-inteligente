from __future__ import annotations

import hashlib
import logging
import math
import re
import sqlite3
import struct
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from atlas.core.config import (
    EMBEDDINGS_ENABLED,
    MEMORY_DB,
    MEMORY_SEMANTIC_CANDIDATES,
    MEMORY_SEMANTIC_MIN_SCORE,
)
from atlas.memory.embeddings import (
    EmbeddingServiceError,
    EmbeddingVector,
    OllamaEmbeddingService,
)
from atlas.memory.models import MemoryRecord, MemorySearchResult

SCHEMA_VERSION = 4
_EMBEDDING_BATCH_SIZE = 64
_SEMANTIC_WEIGHT = 0.65
_LEXICAL_WEIGHT = 0.20
_IMPORTANCE_WEIGHT = 0.10
_RECENCY_WEIGHT = 0.05
_LOGGER = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, text: str) -> EmbeddingVector: ...

    def embed_many(self, texts: list[str]) -> list[EmbeddingVector]: ...

    def close(self) -> None: ...


_MIGRATION_COLUMNS = {
    "category": "TEXT NOT NULL DEFAULT 'general'",
    "source": "TEXT NOT NULL DEFAULT 'user'",
    "importance": "REAL NOT NULL DEFAULT 0.5",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
    "last_accessed_at": "TEXT",
    "access_count": "INTEGER NOT NULL DEFAULT 0",
    "active": "INTEGER NOT NULL DEFAULT 1",
    "memory_key": "TEXT",
    "last_decay_at": "TEXT",
}


class MemoryStore:
    """Repositório SQLite compatível com a memória original do Atlas."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        embedding_service: EmbeddingProvider | None = None,
        semantic_enabled: bool = EMBEDDINGS_ENABLED,
        semantic_min_score: float = MEMORY_SEMANTIC_MIN_SCORE,
        semantic_candidate_limit: int = MEMORY_SEMANTIC_CANDIDATES,
    ) -> None:
        if not 0 <= semantic_min_score <= 1:
            raise ValueError("O score semântico mínimo deve estar entre 0 e 1.")

        if semantic_candidate_limit <= 0:
            raise ValueError("O limite de candidatos deve ser maior que zero.")

        self._lock = threading.RLock()
        self._closed = False
        self._embedding_service = embedding_service
        self._owns_embedding_service = False
        self._semantic_failed = False
        self.semantic_last_error: str | None = None
        self.semantic_enabled = bool(semantic_enabled)
        self.semantic_min_score = float(semantic_min_score)
        self.semantic_candidate_limit = int(semantic_candidate_limit)
        self.database_path = self._resolve_database_path(database_path)
        self.migration_backup: Path | None = None

        self.conn = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    @staticmethod
    def _resolve_database_path(
        database_path: str | Path | None,
    ) -> str:
        if database_path is None:
            return str(MEMORY_DB)

        if str(database_path) == ":memory:":
            return ":memory:"

        path = Path(database_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _initialize_schema(self) -> None:
        with self._lock:
            if not self._table_exists("memories"):
                with self.conn:
                    self._create_memories_table()
                    self._create_embeddings_table()
                    self._create_indexes()
                    self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                return

            columns = self._memory_columns()
            missing_columns = [
                name for name in _MIGRATION_COLUMNS if name not in columns
            ]
            current_version = int(
                self.conn.execute("PRAGMA user_version").fetchone()[0]
            )
            needs_embedding_table = not self._table_exists(
                "memory_embeddings"
            )

            if (
                missing_columns
                or needs_embedding_table
                or current_version < SCHEMA_VERSION
            ):
                self.migration_backup = self._backup_before_migration()

            with self.conn:
                for column in missing_columns:
                    definition = _MIGRATION_COLUMNS[column]
                    self.conn.execute(
                        f"ALTER TABLE memories ADD COLUMN {column} {definition}"
                    )

                now = self._now_text()
                self.conn.execute(
                    """
                    UPDATE memories
                    SET updated_at = CASE
                        WHEN created_at IS NULL OR created_at = '' THEN ?
                        ELSE created_at
                    END
                    WHERE updated_at IS NULL OR updated_at = ''
                    """,
                    (now,),
                )
                self.conn.execute(
                    """
                    UPDATE memories
                    SET last_decay_at = CASE
                        WHEN updated_at IS NOT NULL AND updated_at != ''
                            THEN updated_at
                        WHEN created_at IS NOT NULL AND created_at != ''
                            THEN created_at
                        ELSE ?
                    END
                    WHERE last_decay_at IS NULL OR last_decay_at = ''
                    """,
                    (now,),
                )
                self._create_embeddings_table()
                self._create_indexes()
                self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _table_exists(self, table_name: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def _memory_columns(self) -> set[str]:
        return {
            str(row["name"])
            for row in self.conn.execute(
                "PRAGMA table_info(memories)"
            ).fetchall()
        }

    def _create_memories_table(self) -> None:
        self.conn.execute(
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
                active INTEGER NOT NULL DEFAULT 1,
                memory_key TEXT,
                last_decay_at TEXT
            )
            """
        )

    def _create_embeddings_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                memory_id INTEGER NOT NULL,
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                vector BLOB NOT NULL,
                content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(memory_id, model),
                FOREIGN KEY(memory_id) REFERENCES memories(id)
                    ON DELETE CASCADE
            )
            """
        )

    def _create_indexes(self) -> None:
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memories_active_created
            ON memories(active, created_at DESC)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_embeddings_model
            ON memory_embeddings(model)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memories_category
            ON memories(category)
            """
        )
        self.conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_active_key
            ON memories(memory_key)
            WHERE active = 1 AND memory_key IS NOT NULL
            """
        )

    def _backup_before_migration(self) -> Path | None:
        if self.database_path == ":memory:":
            return None

        database_path = Path(self.database_path)

        if not database_path.is_file():
            return None

        suffix = database_path.suffix or ".db"
        backup_path = database_path.with_name(
            f"{database_path.stem}.pre_schema_v{SCHEMA_VERSION}{suffix}"
        )

        if backup_path.exists():
            return backup_path

        backup_connection = sqlite3.connect(backup_path)

        try:
            self.conn.backup(backup_connection)
        finally:
            backup_connection.close()

        return backup_path

    def remember(self, content: str) -> str:
        """Mantém a resposta textual usada pelo SkillRouter atual."""

        normalized_content = self._normalize_content(content)

        if not normalized_content:
            return "Você não informou o que devo lembrar."

        self.remember_record(normalized_content)
        return f"Certo. Vou lembrar que {normalized_content}."

    def remember_record(
        self,
        content: str,
        *,
        category: str = "general",
        source: str = "user",
        importance: float = 0.5,
        memory_key: str | None = None,
    ) -> MemoryRecord:
        normalized_content = self._normalize_content(content)

        if not normalized_content:
            raise ValueError("O conteúdo da memória não pode ser vazio.")

        normalized_category = self._normalize_label(category, "categoria")
        normalized_source = self._normalize_label(source, "origem")
        normalized_importance = self._validate_importance(importance)
        normalized_memory_key = (
            self._normalize_memory_key(memory_key)
            if memory_key is not None
            else None
        )
        now = self._now_text()

        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO memories(
                    content,
                    category,
                    source,
                    importance,
                    created_at,
                    updated_at,
                    memory_key,
                    last_decay_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_content,
                    normalized_category,
                    normalized_source,
                    normalized_importance,
                    now,
                    now,
                    normalized_memory_key,
                    now,
                ),
            )
            memory_id = int(cursor.lastrowid)
            row = self._select_memory(memory_id, include_inactive=True)

        if row is None:
            raise RuntimeError("A memória criada não pôde ser recuperada.")

        return self._row_to_record(row)

    def get_by_key(self, memory_key: str) -> MemoryRecord | None:
        normalized_key = self._normalize_memory_key(memory_key)

        with self._lock:
            row = self.conn.execute(
                """
                SELECT *
                FROM memories
                WHERE memory_key = ? AND active = 1
                """,
                (normalized_key,),
            ).fetchone()

        return self._row_to_record(row) if row is not None else None

    def upsert_keyed_record(
        self,
        content: str,
        *,
        memory_key: str,
        category: str,
        source: str = "auto_capture",
        importance: float = 0.5,
    ) -> tuple[MemoryRecord, str]:
        """Cria, atualiza ou reaproveita um fato identificado por chave."""

        normalized_content = self._normalize_content(content)

        if not normalized_content:
            raise ValueError("O conteúdo da memória não pode ser vazio.")

        normalized_key = self._normalize_memory_key(memory_key)

        with self._lock:
            existing = self.get_by_key(normalized_key)

            if existing is None:
                created = self.remember_record(
                    normalized_content,
                    category=category,
                    source=source,
                    importance=importance,
                    memory_key=normalized_key,
                )
                return created, "created"

            if (
                existing.content == normalized_content
                and existing.category == self._normalize_label(
                    category,
                    "categoria",
                )
                and existing.source == self._normalize_label(source, "origem")
                and existing.importance == self._validate_importance(importance)
            ):
                return existing, "unchanged"

            updated = self.update(
                existing.id,
                content=normalized_content,
                category=category,
                source=source,
                importance=importance,
            )

            if updated is None:
                raise RuntimeError("A memória automática não pôde ser atualizada.")

            return updated, "updated"

    def get(
        self,
        memory_id: int,
        *,
        include_inactive: bool = False,
    ) -> MemoryRecord | None:
        with self._lock:
            row = self._select_memory(
                memory_id,
                include_inactive=include_inactive,
            )

        return self._row_to_record(row) if row is not None else None

    def list_records(
        self,
        *,
        limit: int = 100,
        include_inactive: bool = False,
    ) -> list[MemoryRecord]:
        normalized_limit = self._validate_limit(limit)
        active_filter = "" if include_inactive else "WHERE active = 1"

        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT *
                FROM memories
                {active_filter}
                ORDER BY id DESC
                LIMIT ?
                """,
                (normalized_limit,),
            ).fetchall()

        return [self._row_to_record(row) for row in rows]

    def list_inactive(self, *, limit: int = 100) -> list[MemoryRecord]:
        normalized_limit = self._validate_limit(limit)

        with self._lock:
            rows = self.conn.execute(
                """
                SELECT *
                FROM memories
                WHERE active = 0
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (normalized_limit,),
            ).fetchall()

        return [self._row_to_record(row) for row in rows]

    def search(
        self,
        query: str,
        limit: int = 6,
    ) -> list[str]:
        return [
            record.content
            for record in self.search_records(query, limit=limit)
        ]

    def search_records(
        self,
        query: str,
        *,
        limit: int = 6,
    ) -> list[MemoryRecord]:
        return [
            result.record
            for result in self.search_detailed(query, limit=limit)
        ]

    def search_detailed(
        self,
        query: str,
        *,
        limit: int = 6,
    ) -> list[MemorySearchResult]:
        """Busca memórias e expõe os sinais usados no ranqueamento."""

        normalized_limit = self._validate_limit(limit)
        normalized_query = " ".join(str(query).split())

        if (
            self.semantic_enabled
            and not self._semantic_failed
            and normalized_query
        ):
            try:
                results = self._hybrid_search(
                    normalized_query,
                    limit=normalized_limit,
                )
            except EmbeddingServiceError as error:
                self._register_semantic_failure(error)
                results = self._lexical_search(
                    normalized_query,
                    limit=normalized_limit,
                )
        else:
            results = self._lexical_search(
                normalized_query,
                limit=normalized_limit,
            )

        if not results:
            return []

        audited = self._audit_access(
            [result.record for result in results]
        )
        audited_by_id = {record.id: record for record in audited}
        return [
            replace(result, record=audited_by_id[result.record.id])
            for result in results
        ]

    def reindex_embeddings(
        self,
        *,
        limit: int | None = None,
        force: bool = False,
    ) -> int:
        """Gera e persiste vetores para as memórias ativas."""

        if not self.semantic_enabled:
            return 0

        normalized_limit = (
            self.semantic_candidate_limit
            if limit is None
            else self._validate_limit(limit)
        )
        records = self._semantic_candidates(normalized_limit)

        if not records:
            return 0

        provider = self._get_embedding_service()
        model = provider.model

        if force:
            memory_ids = [record.id for record in records]
            placeholders = ", ".join("?" for _ in memory_ids)

            with self._lock, self.conn:
                self.conn.execute(
                    f"""
                    DELETE FROM memory_embeddings
                    WHERE model = ? AND memory_id IN ({placeholders})
                    """,
                    [model, *memory_ids],
                )

        _, generated_count = self._vectors_for_records(
            records,
            provider=provider,
            expected_dimensions=None,
        )
        self._semantic_failed = False
        self.semantic_last_error = None
        return generated_count

    def reset_semantic_search(self) -> None:
        """Permite uma nova tentativa após o Ollama voltar a responder."""

        self._semantic_failed = False
        self.semantic_last_error = None

    def _hybrid_search(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[MemorySearchResult]:
        records = self._semantic_candidates(
            max(limit, self.semantic_candidate_limit)
        )

        if not records:
            return []

        provider = self._get_embedding_service()
        query_vector = provider.embed(query)
        vectors, _ = self._vectors_for_records(
            records,
            provider=provider,
            expected_dimensions=query_vector.dimensions,
        )
        results: list[MemorySearchResult] = []

        for record in records:
            memory_vector = vectors.get(record.id)

            if memory_vector is None:
                continue

            semantic_score = self._cosine_similarity(
                query_vector.values,
                memory_vector,
            )
            lexical_score = self._lexical_score(query, record.content)
            recency_score = self._recency_score(record.updated_at)
            score = (
                semantic_score * _SEMANTIC_WEIGHT
                + lexical_score * _LEXICAL_WEIGHT
                + record.importance * _IMPORTANCE_WEIGHT
                + recency_score * _RECENCY_WEIGHT
            )

            if score < self.semantic_min_score:
                continue

            results.append(
                MemorySearchResult(
                    record=record,
                    score=score,
                    semantic_score=semantic_score,
                    lexical_score=lexical_score,
                    importance_score=record.importance,
                    recency_score=recency_score,
                    strategy="hybrid",
                )
            )

        results.sort(
            key=lambda item: (
                item.score,
                item.recency_score,
                item.record.id,
            ),
            reverse=True,
        )
        return results[:limit]

    def _lexical_search(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[MemorySearchResult]:
        records = self._lexical_records(query, limit=limit)
        return [
            MemorySearchResult(
                record=record,
                score=self._lexical_score(query, record.content),
                semantic_score=None,
                lexical_score=self._lexical_score(query, record.content),
                importance_score=record.importance,
                recency_score=self._recency_score(record.updated_at),
                strategy="lexical",
            )
            for record in records
        ]

    def _lexical_records(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[MemoryRecord]:
        words = [
            word
            for word in re.findall(r"\w+", str(query).lower())
            if len(word) >= 4
        ]

        with self._lock:
            if words:
                where = " OR ".join(
                    "LOWER(content) LIKE ?" for _ in words
                )
                params: list[Any] = [f"%{word}%" for word in words]
                params.append(limit)
                rows = self.conn.execute(
                    f"""
                    SELECT *
                    FROM memories
                    WHERE active = 1 AND ({where})
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
            else:
                rows = self.conn.execute(
                    """
                    SELECT *
                    FROM memories
                    WHERE active = 1
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [self._row_to_record(row) for row in rows]

    def _semantic_candidates(self, limit: int) -> list[MemoryRecord]:
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT *
                FROM memories
                WHERE active = 1
                ORDER BY importance DESC, updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._row_to_record(row) for row in rows]

    def _vectors_for_records(
        self,
        records: list[MemoryRecord],
        *,
        provider: EmbeddingProvider,
        expected_dimensions: int | None,
    ) -> tuple[dict[int, tuple[float, ...]], int]:
        model = provider.model
        record_by_id = {record.id: record for record in records}
        memory_ids = list(record_by_id)
        placeholders = ", ".join("?" for _ in memory_ids)
        vectors: dict[int, tuple[float, ...]] = {}

        with self._lock:
            rows = self.conn.execute(
                f"""
                SELECT memory_id, dimensions, vector, content_hash
                FROM memory_embeddings
                WHERE model = ? AND memory_id IN ({placeholders})
                """,
                [model, *memory_ids],
            ).fetchall()

        for row in rows:
            memory_id = int(row["memory_id"])
            record = record_by_id[memory_id]

            if str(row["content_hash"]) != self._content_hash(record.content):
                continue

            dimensions = int(row["dimensions"])

            if (
                expected_dimensions is not None
                and dimensions != expected_dimensions
            ):
                continue

            try:
                vectors[memory_id] = self._deserialize_vector(
                    bytes(row["vector"]),
                    dimensions,
                )
            except ValueError:
                continue

        missing = [record for record in records if record.id not in vectors]
        generated_count = 0

        for start in range(0, len(missing), _EMBEDDING_BATCH_SIZE):
            batch = missing[start : start + _EMBEDDING_BATCH_SIZE]
            generated = provider.embed_many(
                [record.content for record in batch]
            )

            if len(generated) != len(batch):
                raise EmbeddingServiceError(
                    "O provedor retornou uma quantidade inválida de vetores."
                )

            for record, vector in zip(batch, generated, strict=True):
                if (
                    expected_dimensions is not None
                    and vector.dimensions != expected_dimensions
                ):
                    raise EmbeddingServiceError(
                        "O vetor da memória possui dimensão incompatível."
                    )

                vectors[record.id] = vector.values
                self._persist_embedding(
                    record,
                    model=model,
                    values=vector.values,
                )
                generated_count += 1

        return vectors, generated_count

    def _persist_embedding(
        self,
        record: MemoryRecord,
        *,
        model: str,
        values: tuple[float, ...],
    ) -> None:
        blob = self._serialize_vector(values)

        with self._lock, self.conn:
            self.conn.execute(
                """
                INSERT INTO memory_embeddings(
                    memory_id,
                    model,
                    dimensions,
                    vector,
                    content_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id, model) DO UPDATE SET
                    dimensions = excluded.dimensions,
                    vector = excluded.vector,
                    content_hash = excluded.content_hash,
                    created_at = excluded.created_at
                """,
                (
                    record.id,
                    model,
                    len(values),
                    blob,
                    self._content_hash(record.content),
                    self._now_text(),
                ),
            )

    def _audit_access(
        self,
        records: list[MemoryRecord],
    ) -> list[MemoryRecord]:
        if not records:
            return []

        accessed_at = self._now_text()
        placeholders = ", ".join("?" for _ in records)

        with self._lock, self.conn:
            self.conn.execute(
                f"""
                UPDATE memories
                SET access_count = access_count + 1,
                    last_accessed_at = ?
                WHERE id IN ({placeholders})
                """,
                [accessed_at, *(record.id for record in records)],
            )

        accessed_datetime = self._parse_datetime(accessed_at)
        return [
            replace(
                record,
                access_count=record.access_count + 1,
                last_accessed_at=accessed_datetime,
            )
            for record in records
        ]

    def _get_embedding_service(self) -> EmbeddingProvider:
        if self._embedding_service is None:
            self._embedding_service = OllamaEmbeddingService()
            self._owns_embedding_service = True

        return self._embedding_service

    def _register_semantic_failure(self, error: EmbeddingServiceError) -> None:
        self._semantic_failed = True
        self.semantic_last_error = str(error)
        _LOGGER.warning(
            "Busca semântica indisponível; usando busca textual: %s",
            error,
        )

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_vector(values: tuple[float, ...]) -> bytes:
        if not values:
            raise ValueError("O vetor não pode ser vazio.")

        return struct.pack(f"<{len(values)}f", *values)

    @staticmethod
    def _deserialize_vector(blob: bytes, dimensions: int) -> tuple[float, ...]:
        if dimensions <= 0 or len(blob) != dimensions * 4:
            raise ValueError("O vetor persistido é inválido.")

        return tuple(struct.unpack(f"<{dimensions}f", blob))

    @staticmethod
    def _cosine_similarity(
        left: tuple[float, ...],
        right: tuple[float, ...],
    ) -> float:
        if len(left) != len(right) or not left:
            return 0.0

        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))

        if left_norm == 0 or right_norm == 0:
            return 0.0

        similarity = sum(
            left_value * right_value
            for left_value, right_value in zip(left, right, strict=True)
        ) / (left_norm * right_norm)
        return max(0.0, min(1.0, similarity))

    @staticmethod
    def _lexical_score(query: str, content: str) -> float:
        query_tokens = {
            token
            for token in re.findall(r"\w+", query.lower())
            if len(token) >= 3
        }

        if not query_tokens:
            return 0.0

        content_tokens = set(re.findall(r"\w+", content.lower()))
        overlap = len(query_tokens & content_tokens) / len(query_tokens)

        if query.lower() in content.lower():
            return 1.0

        return overlap

    @staticmethod
    def _recency_score(updated_at: datetime) -> float:
        normalized = (
            updated_at.replace(tzinfo=UTC)
            if updated_at.tzinfo is None
            else updated_at.astimezone(UTC)
        )
        age_seconds = max(
            0.0,
            (datetime.now(UTC) - normalized).total_seconds(),
        )
        age_days = age_seconds / 86_400
        return math.exp(-age_days / 180)

    def update(
        self,
        memory_id: int,
        *,
        content: str | None = None,
        category: str | None = None,
        source: str | None = None,
        importance: float | None = None,
    ) -> MemoryRecord | None:
        changes: dict[str, Any] = {}

        if content is not None:
            normalized_content = self._normalize_content(content)

            if not normalized_content:
                raise ValueError("O conteúdo da memória não pode ser vazio.")

            changes["content"] = normalized_content
        if category is not None:
            changes["category"] = self._normalize_label(
                category,
                "categoria",
            )
        if source is not None:
            changes["source"] = self._normalize_label(source, "origem")
        if importance is not None:
            changes["importance"] = self._validate_importance(importance)

        if not changes:
            return self.get(memory_id)

        changed_at = self._now_text()
        changes["updated_at"] = changed_at

        if "content" in changes or "importance" in changes:
            changes["last_decay_at"] = changed_at
        assignments = ", ".join(f"{column} = ?" for column in changes)

        with self._lock, self.conn:
            cursor = self.conn.execute(
                f"""
                UPDATE memories
                SET {assignments}
                WHERE id = ? AND active = 1
                """,
                [*changes.values(), memory_id],
            )

            if cursor.rowcount > 0 and "content" in changes:
                self.conn.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id = ?",
                    (memory_id,),
                )

        if cursor.rowcount == 0:
            return None

        return self.get(memory_id)

    def forget(self, memory_id: int) -> bool:
        """Desativa a memória sem destruir imediatamente seu histórico."""

        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                UPDATE memories
                SET active = 0, updated_at = ?
                WHERE id = ? AND active = 1
                """,
                (self._now_text(), memory_id),
            )

            if cursor.rowcount > 0:
                self.conn.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id = ?",
                    (memory_id,),
                )

        return cursor.rowcount > 0

    def restore(self, memory_id: int) -> bool:
        """Restaura uma memória removida logicamente, quando não há conflito."""

        now = self._now_text()

        try:
            with self._lock, self.conn:
                cursor = self.conn.execute(
                    """
                    UPDATE memories
                    SET active = 1,
                        updated_at = ?,
                        last_decay_at = ?
                    WHERE id = ? AND active = 0
                    """,
                    (now, now, memory_id),
                )
        except sqlite3.IntegrityError:
            return False

        return cursor.rowcount > 0

    def set_decay_state(
        self,
        memory_id: int,
        *,
        importance: float,
        decayed_at: datetime,
    ) -> bool:
        """Atualiza somente a manutenção sem alterar o fato registrado."""

        normalized_importance = self._validate_importance(importance)
        normalized_at = (
            decayed_at.replace(tzinfo=UTC)
            if decayed_at.tzinfo is None
            else decayed_at.astimezone(UTC)
        ).isoformat(timespec="seconds")

        with self._lock, self.conn:
            cursor = self.conn.execute(
                """
                UPDATE memories
                SET importance = ?, last_decay_at = ?
                WHERE id = ? AND active = 1
                """,
                (normalized_importance, normalized_at, memory_id),
            )

        return cursor.rowcount > 0

    def context(self, query: str) -> str:
        return "\n".join(f"- {item}" for item in self.search(query))

    def _select_memory(
        self,
        memory_id: int,
        *,
        include_inactive: bool,
    ) -> sqlite3.Row | None:
        active_filter = "" if include_inactive else "AND active = 1"
        return self.conn.execute(
            f"""
            SELECT *
            FROM memories
            WHERE id = ? {active_filter}
            """,
            (memory_id,),
        ).fetchone()

    @classmethod
    def _row_to_record(cls, row: sqlite3.Row) -> MemoryRecord:
        created_at = cls._parse_datetime(str(row["created_at"]))
        updated_value = str(row["updated_at"] or row["created_at"])
        last_accessed = row["last_accessed_at"]
        last_decay = row["last_decay_at"]

        return MemoryRecord(
            id=int(row["id"]),
            content=str(row["content"]),
            category=str(row["category"]),
            source=str(row["source"]),
            importance=float(row["importance"]),
            created_at=created_at,
            updated_at=cls._parse_datetime(updated_value),
            last_accessed_at=(
                cls._parse_datetime(str(last_accessed))
                if last_accessed
                else None
            ),
            access_count=int(row["access_count"]),
            active=bool(row["active"]),
            memory_key=(
                str(row["memory_key"])
                if row["memory_key"] is not None
                else None
            ),
            last_decay_at=(
                cls._parse_datetime(str(last_decay))
                if last_decay
                else None
            ),
        )

    @staticmethod
    def _normalize_content(content: str) -> str:
        return str(content).strip(" .")

    @staticmethod
    def _normalize_label(value: str, field_name: str) -> str:
        normalized = str(value).strip().lower()

        if not normalized:
            raise ValueError(f"A {field_name} não pode ser vazia.")

        return normalized

    @staticmethod
    def _normalize_memory_key(value: str) -> str:
        normalized = str(value).strip().lower()

        if not normalized:
            raise ValueError("A chave da memória não pode ser vazia.")

        if len(normalized) > 120:
            raise ValueError("A chave da memória pode ter no máximo 120 caracteres.")

        if re.fullmatch(r"[a-z0-9_.:-]+", normalized) is None:
            raise ValueError("A chave da memória contém caracteres inválidos.")

        return normalized

    @staticmethod
    def _validate_importance(importance: float) -> float:
        normalized = float(importance)

        if not 0 <= normalized <= 1:
            raise ValueError("A importância deve estar entre 0 e 1.")

        return normalized

    @staticmethod
    def _validate_limit(limit: int) -> int:
        normalized = int(limit)

        if normalized <= 0:
            raise ValueError("O limite deve ser maior que zero.")

        return normalized

    @staticmethod
    def _now_text() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds")

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return

            if (
                self._owns_embedding_service
                and self._embedding_service is not None
            ):
                self._embedding_service.close()

            self.conn.close()
            self._closed = True

    def __enter__(self) -> MemoryStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
