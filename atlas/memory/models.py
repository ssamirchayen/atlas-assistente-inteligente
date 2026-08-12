from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """Representação estruturada e imutável de uma memória do Atlas."""

    id: int
    content: str
    category: str
    source: str
    importance: float
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None
    access_count: int
    active: bool
    memory_key: str | None = None
    last_decay_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "source": self.source,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_accessed_at": (
                self.last_accessed_at.isoformat()
                if self.last_accessed_at is not None
                else None
            ),
            "access_count": self.access_count,
            "active": self.active,
            "memory_key": self.memory_key,
            "last_decay_at": (
                self.last_decay_at.isoformat()
                if self.last_decay_at is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    """Memória acompanhada dos sinais usados no ranqueamento."""

    record: MemoryRecord
    score: float
    semantic_score: float | None
    lexical_score: float
    importance_score: float
    recency_score: float
    strategy: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "memory": self.record.as_dict(),
            "score": self.score,
            "semantic_score": self.semantic_score,
            "lexical_score": self.lexical_score,
            "importance_score": self.importance_score,
            "recency_score": self.recency_score,
            "strategy": self.strategy,
        }
