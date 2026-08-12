from __future__ import annotations

from pathlib import Path

import pytest

from atlas.memory.automatic import (
    AutoMemoryManager,
    AutomaticMemoryExtractor,
)
from atlas.memory.database import MemoryStore


def test_extractor_finds_profile_fact() -> None:
    extractor = AutomaticMemoryExtractor(user_name="Ssamir")

    candidates = extractor.extract("Eu moro em Manaus")

    assert len(candidates) == 1
    assert candidates[0].content == "Ssamir mora em Manaus"
    assert candidates[0].category == "profile"
    assert candidates[0].memory_key == "profile.location"
    assert candidates[0].confidence == 0.96


def test_extractor_removes_wake_word_and_finds_multiple_facts() -> None:
    extractor = AutomaticMemoryExtractor(user_name="Ssamir")

    candidates = extractor.extract(
        "Atlas, eu moro em Manaus e trabalho como vendedor"
    )

    assert [candidate.memory_key for candidate in candidates] == [
        "profile.location",
        "work.role",
    ]
    assert [candidate.content for candidate in candidates] == [
        "Ssamir mora em Manaus",
        "Ssamir trabalha como vendedor",
    ]


@pytest.mark.parametrize(
    ("text", "category", "memory_key", "content"),
    [
        (
            "Meu nome é Ssamir Martins",
            "profile",
            "profile.name",
            "O nome do usuário é Ssamir Martins",
        ),
        (
            "Eu nasci em Manaus",
            "profile",
            "profile.birthplace",
            "Ssamir nasceu em Manaus",
        ),
        (
            "Tenho 25 anos",
            "profile",
            "profile.age",
            "Ssamir tem 25 anos",
        ),
        (
            "Trabalho no Grau Técnico",
            "work",
            "work.company",
            "Ssamir trabalha em Grau Técnico",
        ),
        (
            "Eu faço faculdade de ADS",
            "education",
            "education:ads",
            "Ssamir cursa ADS",
        ),
        (
            "Meu projeto se chama Atlas",
            "project",
            "project.current",
            "O projeto atual de Ssamir é Atlas",
        ),
        (
            "Eu gosto de café",
            "preference",
            "preference:cafe",
            "Ssamir gosta de café",
        ),
        (
            "Meu objetivo é trabalhar com tecnologia",
            "goal",
            "goal:trabalhar-com-tecnologia",
            "Um objetivo de Ssamir é trabalhar com tecnologia",
        ),
    ],
)
def test_extractor_classifies_supported_facts(
    text: str,
    category: str,
    memory_key: str,
    content: str,
) -> None:
    candidate = AutomaticMemoryExtractor(user_name="Ssamir").extract(text)[0]

    assert candidate.category == category
    assert candidate.memory_key == memory_key
    assert candidate.content == content


def test_preference_polarity_uses_same_key() -> None:
    extractor = AutomaticMemoryExtractor(user_name="Ssamir")

    positive = extractor.extract("Eu gosto de café")[0]
    negative = extractor.extract("Eu não gosto de café")[0]

    assert positive.memory_key == negative.memory_key == "preference:cafe"
    assert positive.content == "Ssamir gosta de café"
    assert negative.content == "Ssamir não gosta de café"


@pytest.mark.parametrize(
    "text",
    [
        "Qual cidade eu moro?",
        "Abra o navegador",
        "Pesquise carros usados",
        "Lembre que eu moro em Manaus",
        "Não salve que eu moro em Manaus",
        "Esqueça essa informação, eu moro em Manaus",
        "",
    ],
)
def test_questions_commands_and_denials_are_not_captured(text: str) -> None:
    extractor = AutomaticMemoryExtractor()

    assert extractor.extract(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Minha senha é segredo e eu moro em Manaus",
        "Meu CPF é 123 e eu moro em Manaus",
        "Tenho uma doença e moro em Manaus",
        "Minha chave Pix está salva e eu moro em Manaus",
    ],
)
def test_sensitive_statements_are_blocked_by_default(text: str) -> None:
    extractor = AutomaticMemoryExtractor()

    assert extractor.extract(text) == []


def test_sensitive_filter_can_be_explicitly_relaxed() -> None:
    extractor = AutomaticMemoryExtractor(
        user_name="Ssamir",
        allow_sensitive=True,
    )

    candidates = extractor.extract(
        "Minha senha está protegida e eu moro em Manaus"
    )

    assert [candidate.memory_key for candidate in candidates] == [
        "profile.location"
    ]


def test_confidence_threshold_filters_weaker_rules() -> None:
    extractor = AutomaticMemoryExtractor(
        minimum_confidence=0.95,
    )

    assert extractor.extract("Eu moro em Manaus")
    assert extractor.extract("Meu objetivo é trabalhar com tecnologia") == []


def test_manager_creates_updates_and_deduplicates_fact(tmp_path: Path) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        manager = AutoMemoryManager(
            memory,
            extractor=AutomaticMemoryExtractor(user_name="Ssamir"),
        )

        created = manager.capture("Eu moro em Manaus")
        unchanged = manager.capture("Eu moro em Manaus")
        updated = manager.capture("Agora eu moro em São Paulo")
        records = memory.list_records()

    assert created.created == 1
    assert unchanged.unchanged == 1
    assert updated.updated == 1
    assert len(records) == 1
    assert records[0].content == "Ssamir mora em São Paulo"
    assert records[0].memory_key == "profile.location"
    assert records[0].source == "auto_capture"


def test_manager_keeps_different_education_facts(tmp_path: Path) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        manager = AutoMemoryManager(memory)

        manager.capture("Eu estudo Radiologia")
        manager.capture("Eu faço faculdade de ADS")
        records = memory.list_records()

    assert len(records) == 2
    assert {record.memory_key for record in records} == {
        "education:radiologia",
        "education:ads",
    }


def test_updated_automatic_fact_invalidates_old_embedding(
    tmp_path: Path,
) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        manager = AutoMemoryManager(memory)
        manager.capture("Eu moro em Manaus")
        record = memory.get_by_key("profile.location")
        assert record is not None

        memory.conn.execute(
            """
            INSERT INTO memory_embeddings(
                memory_id, model, dimensions, vector, content_hash, created_at
            ) VALUES (?, 'fake', 1, ?, 'hash', '2026-08-06T00:00:00+00:00')
            """,
            (record.id, b"1234"),
        )
        memory.conn.commit()

        manager.capture("Eu moro em São Paulo")
        count = memory.conn.execute(
            "SELECT COUNT(*) FROM memory_embeddings"
        ).fetchone()[0]

    assert count == 0


def test_keyed_memory_survives_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.db"

    with MemoryStore(database_path, semantic_enabled=False) as memory:
        AutoMemoryManager(memory).capture("Eu moro em Manaus")

    with MemoryStore(database_path, semantic_enabled=False) as reopened:
        record = reopened.get_by_key("profile.location")

    assert record is not None
    assert record.content == "Ssamir mora em Manaus"


def test_disabled_manager_does_not_write(tmp_path: Path) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        result = AutoMemoryManager(memory, enabled=False).capture(
            "Eu moro em Manaus"
        )

        assert result.ignored_reason == "disabled"
        assert memory.list_records() == []


def test_no_candidate_is_reported_without_writing(tmp_path: Path) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        result = AutoMemoryManager(memory).capture("Abra o navegador")

        assert result.ignored_reason == "no_candidate"
        assert result.records == ()


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_extractor_validates_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="entre 0 e 1"):
        AutomaticMemoryExtractor(minimum_confidence=confidence)


@pytest.mark.parametrize(
    "memory_key",
    ["", "chave com espaços", "chave/ruim", "x" * 121],
)
def test_memory_store_rejects_invalid_keys(
    tmp_path: Path,
    memory_key: str,
) -> None:
    with MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    ) as memory:
        with pytest.raises(ValueError, match="chave"):
            memory.remember_record("Fato", memory_key=memory_key)
