from __future__ import annotations

import pytest

from atlas.gui.single_instance import SingleInstanceGuard


class FakeSharedMemory:
    def __init__(self, _key: str, *, can_create: bool = True) -> None:
        self.can_create = can_create
        self.attached = False
        self.detach_calls = 0

    def create(self, _size: int) -> bool:
        if not self.can_create:
            return False
        self.attached = True
        return True

    def isAttached(self) -> bool:
        return self.attached

    def detach(self) -> bool:
        self.detach_calls += 1
        self.attached = False
        return True


def test_first_instance_acquires_guard() -> None:
    memory = FakeSharedMemory("atlas")
    guard = SingleInstanceGuard("atlas", memory_factory=lambda _key: memory)

    assert guard.acquire() is True


def test_second_instance_is_rejected() -> None:
    memory = FakeSharedMemory("atlas", can_create=False)
    guard = SingleInstanceGuard("atlas", memory_factory=lambda _key: memory)

    assert guard.acquire() is False


def test_guard_releases_shared_memory() -> None:
    memory = FakeSharedMemory("atlas")
    guard = SingleInstanceGuard("atlas", memory_factory=lambda _key: memory)

    assert guard.acquire() is True
    guard.release()

    assert memory.attached is False
    assert memory.detach_calls == 1


def test_empty_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="não pode ser vazia"):
        SingleInstanceGuard("   ", memory_factory=FakeSharedMemory)
