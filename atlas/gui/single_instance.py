"""Proteção de instância única para a interface gráfica do Atlas."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class SharedMemoryHandle(Protocol):
    def create(self, size: int) -> bool: ...

    def isAttached(self) -> bool: ...

    def detach(self) -> bool: ...


class SingleInstanceGuard:
    """Mantém apenas uma GUI do Atlas ativa por sessão do sistema."""

    def __init__(
        self,
        key: str,
        *,
        memory_factory: Callable[[str], SharedMemoryHandle] | None = None,
    ) -> None:
        if not key.strip():
            raise ValueError("A chave da instância não pode ser vazia.")

        if memory_factory is None:
            from PySide6.QtCore import QSharedMemory

            memory_factory = QSharedMemory

        self._memory = memory_factory(key)
        self._acquired = False

    def acquire(self) -> bool:
        """Retorna True somente para a primeira instância ativa."""
        if self._acquired:
            return True

        self._acquired = bool(self._memory.create(1))
        return self._acquired

    def release(self) -> None:
        """Libera o marcador quando a aplicação é encerrada normalmente."""
        if not self._acquired:
            return

        if self._memory.isAttached():
            self._memory.detach()

        self._acquired = False
