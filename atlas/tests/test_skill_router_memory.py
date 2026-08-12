from __future__ import annotations

from pathlib import Path

from atlas.memory.database import MemoryStore
from atlas.memory.lifecycle import MemoryLifecycleManager
from atlas.skills.router import SkillRouter


def make_router(tmp_path: Path) -> tuple[MemoryStore, SkillRouter]:
    memory = MemoryStore(
        tmp_path / "memory.db",
        semantic_enabled=False,
    )
    lifecycle = MemoryLifecycleManager(memory, user_name="Ssamir")
    return memory, SkillRouter(memory, lifecycle)


def test_router_keeps_explicit_remember_command(tmp_path: Path) -> None:
    memory, router = make_router(tmp_path)

    try:
        result = router.route("Lembre que meu carro é um Gol")
        records = memory.list_records()
    finally:
        memory.close()

    assert result.handled is True
    assert result.message == "Certo. Vou lembrar que meu carro e um gol."
    assert len(records) == 1


def test_explicit_remember_is_available_in_priority_route(
    tmp_path: Path,
) -> None:
    memory, router = make_router(tmp_path)

    try:
        result = router.route_priority(
            "Lembre que minha sobremesa favorita é pudim de cupuaçu"
        )
        records = memory.list_records()
    finally:
        memory.close()

    assert result.handled is True
    assert "pudim de cupuacu" in result.message
    assert len(records) == 1
    assert records[0].content.endswith("pudim de cupuacu")


def test_non_memory_command_does_not_use_priority_route(tmp_path: Path) -> None:
    memory, router = make_router(tmp_path)

    try:
        result = router.route_priority("pesquise carros usados")
        records = memory.list_records()
    finally:
        memory.close()

    assert result.handled is False
    assert records == []


def test_spoken_delete_is_handled_in_priority_route(tmp_path: Path) -> None:
    memory, router = make_router(tmp_path)

    try:
        record = memory.remember_record("Sobremesa favorita: pudim")
        result = router.route_priority(f"apaga memoria {record.id}")
        inactive = memory.get(record.id, include_inactive=True)
    finally:
        memory.close()

    assert result.handled is True
    assert "removida" in result.message
    assert inactive is not None
    assert inactive.active is False


def test_invalid_memory_admin_command_never_reaches_planner(
    tmp_path: Path,
) -> None:
    memory, router = make_router(tmp_path)

    try:
        result = router.route_priority("apaga memoria do celular")
    finally:
        memory.close()

    assert result.handled is True
    assert "use o número" in result.message


def test_router_lists_managed_memories(tmp_path: Path) -> None:
    memory, router = make_router(tmp_path)

    try:
        record = memory.remember_record(
            "Ssamir mora em Manaus",
            category="profile",
        )

        result = router.route("Mostre minhas memórias")
    finally:
        memory.close()

    assert result.handled is True
    assert f"#{record.id} [profile]" in result.message


def test_router_corrects_deletes_and_restores_memory(tmp_path: Path) -> None:
    memory, router = make_router(tmp_path)

    try:
        corrected = router.route("Corrija minha cidade para Manaus")
        record = memory.get_by_key("profile.location")
        assert record is not None

        removed = router.route(f"Apague a memória {record.id}")
        restored = router.route(f"Restaure a memória {record.id}")
        active = memory.get(record.id)
    finally:
        memory.close()

    assert corrected.handled is True
    assert removed.handled is True
    assert restored.handled is True
    assert active is not None


def test_router_ignores_unrelated_command(tmp_path: Path) -> None:
    memory, router = make_router(tmp_path)

    try:
        result = router.route("conte uma história")
    finally:
        memory.close()

    assert result.handled is False
