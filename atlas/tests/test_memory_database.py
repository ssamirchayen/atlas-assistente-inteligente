from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atlas.memory.database import SCHEMA_VERSION, MemoryStore


def test_legacy_memory_api_remains_compatible(tmp_path: Path) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        response = memory.remember(" Ssamir estuda ADS. ")

        assert response == "Certo. Vou lembrar que Ssamir estuda ADS."
        assert memory.search("Onde Ssamir estuda?") == [
            "Ssamir estuda ADS"
        ]
        assert memory.context("Ssamir") == "- Ssamir estuda ADS"


def test_structured_memory_can_be_created_and_persisted(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "memory.db"

    with MemoryStore(database_path, semantic_enabled=False) as memory:
        created = memory.remember_record(
            "Ssamir prefere respostas objetivas",
            category="preference",
            source="explicit_command",
            importance=0.9,
        )

        assert created.category == "preference"
        assert created.source == "explicit_command"
        assert created.importance == 0.9
        assert created.active is True
        assert created.access_count == 0

    with MemoryStore(database_path, semantic_enabled=False) as reopened:
        persisted = reopened.get(created.id)

    assert persisted is not None
    assert persisted.content == "Ssamir prefere respostas objetivas"
    assert persisted.created_at == created.created_at


def test_existing_database_is_migrated_with_backup(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO memories(content, created_at)
        VALUES (?, ?)
        """,
        ("Ssamir trabalha no Atlas", "2026-08-06T00:00:00"),
    )
    connection.commit()
    connection.close()

    with MemoryStore(database_path, semantic_enabled=False) as memory:
        migrated = memory.get(1)
        backup_path = memory.migration_backup
        version = memory.conn.execute("PRAGMA user_version").fetchone()[0]

    assert migrated is not None
    assert migrated.content == "Ssamir trabalha no Atlas"
    assert migrated.category == "general"
    assert migrated.source == "user"
    assert migrated.importance == 0.5
    assert migrated.active is True
    assert version == SCHEMA_VERSION
    assert backup_path is not None
    assert backup_path.is_file()

    backup_connection = sqlite3.connect(backup_path)
    backup_columns = {
        row[1]
        for row in backup_connection.execute(
            "PRAGMA table_info(memories)"
        ).fetchall()
    }
    backup_connection.close()

    assert backup_columns == {"id", "content", "created_at"}


def test_search_records_audits_memory_access(tmp_path: Path) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        created = memory.remember_record("Ssamir mora em Manaus")
        matches = memory.search_records("Qual cidade Ssamir mora?")
        persisted = memory.get(created.id)

    assert len(matches) == 1
    assert matches[0].access_count == 1
    assert matches[0].last_accessed_at is not None
    assert persisted is not None
    assert persisted.access_count == 1


def test_memory_can_be_updated_and_soft_deleted(tmp_path: Path) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        created = memory.remember_record("Curso antigo")
        updated = memory.update(
            created.id,
            content="Curso de ADS na Uninter",
            category="education",
            importance=0.8,
        )

        assert updated is not None
        assert updated.content == "Curso de ADS na Uninter"
        assert updated.category == "education"
        assert updated.importance == 0.8
        assert memory.forget(created.id) is True
        assert memory.forget(created.id) is False
        assert memory.get(created.id) is None

        inactive = memory.get(created.id, include_inactive=True)

    assert inactive is not None
    assert inactive.active is False


@pytest.mark.parametrize("importance", [-0.1, 1.1])
def test_memory_rejects_invalid_importance(
    tmp_path: Path,
    importance: float,
) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        with pytest.raises(ValueError, match="entre 0 e 1"):
            memory.remember_record("Memória", importance=importance)


def test_memory_close_is_idempotent(tmp_path: Path) -> None:
    memory = MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    )

    memory.close()
    memory.close()
