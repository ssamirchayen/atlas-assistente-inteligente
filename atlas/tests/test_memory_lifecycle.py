from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from atlas.memory.database import MemoryStore
from atlas.memory.lifecycle import MemoryLifecycleManager


def make_manager(
    tmp_path: Path,
    **kwargs: object,
) -> tuple[MemoryStore, MemoryLifecycleManager]:
    memory = MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    )
    manager = MemoryLifecycleManager(
        memory,
        user_name="Ssamir",
        **kwargs,
    )
    return memory, manager


def test_list_command_shows_ids_categories_and_contents(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        first = memory.remember_record(
            "Ssamir mora em Manaus",
            category="profile",
        )
        second = memory.remember_record(
            "Ssamir estuda ADS",
            category="education",
        )

        result = manager.handle_command("Mostre minhas memórias")
    finally:
        memory.close()

    assert result.handled is True
    assert f"#{first.id} [profile] Ssamir mora em Manaus" in result.message
    assert f"#{second.id} [education] Ssamir estuda ADS" in result.message


def test_list_command_reports_empty_memory(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        result = manager.handle_command("quais são minhas memórias")
    finally:
        memory.close()

    assert result.message == "Ainda não tenho memórias salvas."


def test_spoken_singular_list_command_shows_real_memory_id(
    tmp_path: Path,
) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record("Sobremesa favorita: pudim")
        result = manager.handle_command("liste minha memoria")
    finally:
        memory.close()

    assert result.handled is True
    assert f"#{record.id} [general]" in result.message


def test_delete_and_restore_memory_by_id(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record("Fato recuperável")

        removed = manager.handle_command(f"apague a memória {record.id}")
        assert memory.get(record.id) is None
        assert memory.get(record.id, include_inactive=True) is not None

        restored = manager.handle_command(f"restaure a memória {record.id}")
        active = memory.get(record.id)
    finally:
        memory.close()

    assert removed.handled is True
    assert "pode ser restaurada" in removed.message
    assert restored.message == f"Memória #{record.id} restaurada."
    assert active is not None


def test_spoken_delete_and_restore_variants_by_id(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record("Sobremesa favorita: pudim")

        removed = manager.handle_command(f"apaga memoria {record.id}")
        inactive = memory.get(record.id, include_inactive=True)
        restored = manager.handle_command(f"restaura memoria {record.id}")
        active = memory.get(record.id)
    finally:
        memory.close()

    assert removed.handled is True
    assert inactive is not None
    assert inactive.active is False
    assert restored.handled is True
    assert active is not None


def test_deleted_memory_list_supports_restoration_workflow(
    tmp_path: Path,
) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record("Memória removida")
        memory.forget(record.id)

        result = manager.handle_command("listar memórias apagadas")
    finally:
        memory.close()

    assert result.handled is True
    assert f"#{record.id} [general] Memória removida" in result.message


@pytest.mark.parametrize(
    "command",
    [
        "liste as memórias apagadas",
        "liste a memória apagada",
        "mostre minhas memórias removidas",
        "quais memórias foram excluídas",
        "memórias deletadas",
    ],
)
def test_deleted_memory_list_accepts_natural_variations(
    tmp_path: Path,
    command: str,
) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record("Sobremesa favorita: pudim")
        memory.forget(record.id)
        result = manager.handle_command(command)
    finally:
        memory.close()

    assert result.handled is True
    assert result.message.startswith("Memórias apagadas:")
    assert f"#{record.id} [general]" in result.message


def test_restore_fails_when_active_key_conflicts(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        old = memory.remember_record(
            "Ssamir mora em Manaus",
            memory_key="profile.location",
        )
        memory.forget(old.id)
        memory.remember_record(
            "Ssamir mora em São Paulo",
            memory_key="profile.location",
        )

        result = manager.handle_command(f"restaure memória {old.id}")
    finally:
        memory.close()

    assert "Não foi possível" in result.message


def test_correct_memory_by_id_preserves_raw_value(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record("Curso antigo")

        result = manager.handle_command(
            f"Corrija a memória {record.id} para Análise e Desenvolvimento"
        )
        updated = memory.get(record.id)
    finally:
        memory.close()

    assert result.handled is True
    assert updated is not None
    assert updated.content == "Análise e Desenvolvimento"


def test_correct_known_field_creates_or_updates_single_fact(
    tmp_path: Path,
) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        created = manager.handle_command(
            "Corrija minha cidade para Manaus"
        )
        updated = manager.handle_command(
            "Atualize minha cidade para São Paulo"
        )
        records = memory.list_records()
    finally:
        memory.close()

    assert "criada" in created.message
    assert "corrigida" in updated.message
    assert len(records) == 1
    assert records[0].content == "Ssamir mora em São Paulo"
    assert records[0].memory_key == "profile.location"
    assert records[0].source == "user_correction"


def test_age_correction_adds_unit_only_when_needed(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        manager.handle_command("Corrija minha idade para 26")
        first = memory.get_by_key("profile.age")
        manager.handle_command("Corrija minha idade para 27 anos")
        second = memory.get_by_key("profile.age")
    finally:
        memory.close()

    assert first is not None
    assert first.content == "Ssamir tem 26 anos"
    assert second is not None
    assert second.content == "Ssamir tem 27 anos"


def test_remove_known_field_by_alias(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record(
            "Ssamir trabalha como vendedor",
            category="work",
            memory_key="work.role",
        )

        result = manager.handle_command("Esqueça minha profissão")
        inactive = memory.get(record.id, include_inactive=True)
    finally:
        memory.close()

    assert result.handled is True
    assert inactive is not None
    assert inactive.active is False


def test_forget_matching_fact_requests_id_when_ambiguous(
    tmp_path: Path,
) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        first = memory.remember_record("Ssamir estuda ADS")
        second = memory.remember_record("Ssamir estuda Radiologia")

        result = manager.handle_command("Esqueça que Ssamir estuda")
    finally:
        memory.close()

    assert f"#{first.id}" in result.message
    assert f"#{second.id}" in result.message
    assert "mais de uma possibilidade" in result.message


def test_forget_matching_unique_fact(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        record = memory.remember_record("Ssamir mora em Manaus")

        result = manager.handle_command(
            "Esqueça que Ssamir mora em Manaus"
        )
        active = memory.get(record.id)
    finally:
        memory.close()

    assert result.handled is True
    assert active is None


def test_consolidation_soft_deletes_near_duplicate(tmp_path: Path) -> None:
    memory, manager = make_manager(
        tmp_path,
        consolidation_threshold=0.85,
    )

    try:
        keeper = memory.remember_record(
            "Ssamir prefere respostas objetivas",
            category="preference",
            importance=0.9,
        )
        duplicate = memory.remember_record(
            "Ssamir prefere resposta objetiva",
            category="preference",
            importance=0.5,
        )

        report = manager.consolidate()
        active_ids = {record.id for record in memory.list_records()}
        deleted = memory.get(duplicate.id, include_inactive=True)
    finally:
        memory.close()

    assert report.removed_ids == (duplicate.id,)
    assert keeper.id in active_ids
    assert duplicate.id not in active_ids
    assert deleted is not None
    assert deleted.active is False


def test_consolidation_dry_run_does_not_modify_database(
    tmp_path: Path,
) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        memory.remember_record("Memória igual")
        memory.remember_record("Memória igual")

        report = manager.consolidate(dry_run=True)
        active = memory.list_records()
    finally:
        memory.close()

    assert len(report.groups) == 1
    assert report.removed_ids == ()
    assert len(active) == 2


def test_consolidation_never_merges_different_categories_or_keys(
    tmp_path: Path,
) -> None:
    memory, manager = make_manager(tmp_path)

    try:
        memory.remember_record("Mesmo conteúdo", category="work")
        memory.remember_record("Mesmo conteúdo", category="profile")
        memory.remember_record(
            "Ssamir estuda ADS",
            category="education",
            memory_key="education:ads",
        )
        memory.remember_record(
            "Ssamir estuda ADS",
            category="education",
            memory_key="education:radiologia",
        )

        report = manager.consolidate()
    finally:
        memory.close()

    assert report.removed_ids == ()


def test_decay_halves_old_importance_after_half_life(tmp_path: Path) -> None:
    memory, manager = make_manager(
        tmp_path,
        half_life_days=100,
        importance_floor=0.1,
    )
    now = datetime(2026, 8, 6, tzinfo=UTC)
    old = now - timedelta(days=100)

    try:
        record = memory.remember_record("Memória antiga", importance=0.8)
        memory.conn.execute(
            """
            UPDATE memories
            SET updated_at = ?, last_decay_at = ?, last_accessed_at = NULL
            WHERE id = ?
            """,
            (old.isoformat(), old.isoformat(), record.id),
        )
        memory.conn.commit()

        report = manager.run_decay(now=now)
        decayed = memory.get(record.id)
    finally:
        memory.close()

    assert report.updated == 1
    assert decayed is not None
    assert decayed.importance == pytest.approx(0.4)
    assert decayed.last_decay_at == now


def test_decay_respects_floor_and_recent_access(tmp_path: Path) -> None:
    memory, manager = make_manager(
        tmp_path,
        half_life_days=10,
        importance_floor=0.2,
    )
    now = datetime(2026, 8, 6, tzinfo=UTC)
    old = now - timedelta(days=100)

    try:
        floor_record = memory.remember_record("Muito antiga", importance=0.3)
        recent_record = memory.remember_record("Acessada agora", importance=0.8)
        memory.conn.execute(
            """
            UPDATE memories
            SET updated_at = ?, last_decay_at = ?, last_accessed_at = NULL
            WHERE id = ?
            """,
            (old.isoformat(), old.isoformat(), floor_record.id),
        )
        memory.conn.execute(
            """
            UPDATE memories
            SET updated_at = ?, last_decay_at = ?, last_accessed_at = ?
            WHERE id = ?
            """,
            (old.isoformat(), old.isoformat(), now.isoformat(), recent_record.id),
        )
        memory.conn.commit()

        manager.run_decay(now=now)
        floor_result = memory.get(floor_record.id)
        recent_result = memory.get(recent_record.id)
    finally:
        memory.close()

    assert floor_result is not None
    assert floor_result.importance == 0.2
    assert recent_result is not None
    assert recent_result.importance == 0.8


def test_disabled_decay_leaves_all_priorities_unchanged(tmp_path: Path) -> None:
    memory, manager = make_manager(tmp_path, decay_enabled=False)

    try:
        record = memory.remember_record("Memória", importance=0.7)
        report = manager.run_decay(
            now=datetime(2030, 1, 1, tzinfo=UTC),
        )
        persisted = memory.get(record.id)
    finally:
        memory.close()

    assert report.updated == 0
    assert persisted is not None
    assert persisted.importance == 0.7


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"half_life_days": 0}, "meia-vida"),
        ({"importance_floor": -0.1}, "piso"),
        ({"importance_floor": 1.1}, "piso"),
        ({"consolidation_threshold": 0.4}, "limiar"),
        ({"consolidation_threshold": 1.1}, "limiar"),
    ],
)
def test_lifecycle_configuration_is_validated(
    tmp_path: Path,
    kwargs: dict[str, float],
    message: str,
) -> None:
    memory = MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    )

    try:
        with pytest.raises(ValueError, match=message):
            MemoryLifecycleManager(memory, **kwargs)
    finally:
        memory.close()
