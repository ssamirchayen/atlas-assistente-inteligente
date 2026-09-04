"""Carregamento tardio explícito, thread-safe e observável."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from threading import Condition, RLock, get_ident
from time import monotonic
from typing import Any, Generic, TypeVar
import re


T = TypeVar("T")
_COMPONENT_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")


class LazyState(StrEnum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LazySnapshot:
    name: str
    state: LazyState
    load_attempts: int
    successful_loads: int
    load_duration_ms: float | None
    last_error_type: str | None

    @property
    def loaded(self) -> bool:
        return self.state is LazyState.READY


class LazyLoadError(RuntimeError):
    def __init__(self, component_name: str, error_type: str) -> None:
        self.component_name = component_name
        self.error_type = error_type
        super().__init__(
            f"Falha ao carregar o componente '{component_name}' ({error_type})."
        )


class LazyRecursiveLoadError(RuntimeError):
    pass


class LazyComponent(Generic[T]):
    """Executa a factory uma vez e compartilha o resultado entre threads."""

    def __init__(self, name: str, factory: Callable[[], T]) -> None:
        if not isinstance(name, str) or not _COMPONENT_NAME.fullmatch(name):
            raise ValueError("Nome de componente lazy inválido.")
        if not callable(factory):
            raise TypeError("factory deve ser chamável.")
        self.name = name
        self._factory = factory
        self._state = LazyState.UNLOADED
        self._instance: T | None = None
        self._load_attempts = 0
        self._successful_loads = 0
        self._load_duration_ms: float | None = None
        self._last_error_type: str | None = None
        self._loading_thread_id: int | None = None
        self._condition = Condition(RLock())

    @property
    def loaded(self) -> bool:
        with self._condition:
            return self._state is LazyState.READY

    def peek(self) -> T | None:
        with self._condition:
            return self._instance if self._state is LazyState.READY else None

    def get(self) -> T:
        current_thread = get_ident()
        with self._condition:
            while self._state is LazyState.LOADING:
                if self._loading_thread_id == current_thread:
                    raise LazyRecursiveLoadError(
                        f"Carregamento recursivo detectado em '{self.name}'."
                    )
                self._condition.wait()

            if self._state is LazyState.READY:
                if self._instance is None:
                    raise RuntimeError("Estado lazy inconsistente.")
                return self._instance

            if self._state is LazyState.FAILED:
                raise LazyLoadError(
                    self.name,
                    self._last_error_type or "UnknownError",
                )

            self._state = LazyState.LOADING
            self._loading_thread_id = current_thread
            self._load_attempts += 1

        started_at = monotonic()
        try:
            instance = self._factory()
            if instance is None:
                raise TypeError("A factory retornou None.")
        except Exception as error:
            duration = max(0.0, (monotonic() - started_at) * 1000)
            with self._condition:
                self._state = LazyState.FAILED
                self._load_duration_ms = duration
                self._last_error_type = type(error).__name__
                self._loading_thread_id = None
                self._condition.notify_all()
            raise LazyLoadError(self.name, type(error).__name__) from error

        duration = max(0.0, (monotonic() - started_at) * 1000)
        with self._condition:
            self._instance = instance
            self._state = LazyState.READY
            self._successful_loads += 1
            self._load_duration_ms = duration
            self._last_error_type = None
            self._loading_thread_id = None
            self._condition.notify_all()
            return instance

    def reset_failure(self) -> bool:
        """Libera uma falha armazenada; nunca descarrega instância pronta."""

        with self._condition:
            if self._state is not LazyState.FAILED:
                return False
            self._state = LazyState.UNLOADED
            self._last_error_type = None
            self._load_duration_ms = None
            return True

    def snapshot(self) -> LazySnapshot:
        with self._condition:
            return LazySnapshot(
                name=self.name,
                state=self._state,
                load_attempts=self._load_attempts,
                successful_loads=self._successful_loads,
                load_duration_ms=self._load_duration_ms,
                last_error_type=self._last_error_type,
            )


class LazyProxy(Generic[T]):
    """Preserva a interface pública enquanto adia a instanciação."""

    __slots__ = ("_component",)

    def __init__(self, component: LazyComponent[T]) -> None:
        object.__setattr__(self, "_component", component)

    @property
    def component(self) -> LazyComponent[T]:
        return object.__getattribute__(self, "_component")

    def unwrap(self) -> T:
        return self.component.get()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.unwrap(), name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.unwrap()(*args, **kwargs)  # type: ignore[operator]

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        snapshot = self.component.snapshot()
        return f"LazyProxy(name={snapshot.name!r}, state={snapshot.state.value!r})"


class LazyComponentRegistry:
    def __init__(self, components: Iterable[LazyComponent[Any]]) -> None:
        items = tuple(components)
        if not items:
            raise ValueError("O registro lazy não pode ser vazio.")
        by_name = {component.name: component for component in items}
        if len(by_name) != len(items):
            raise ValueError("O registro lazy não aceita nomes duplicados.")
        self._components = by_name

    def get(self, name: str) -> LazyComponent[Any]:
        try:
            return self._components[name]
        except KeyError as exc:
            raise KeyError(f"Componente lazy desconhecido: {name}") from exc

    def snapshots(self) -> tuple[LazySnapshot, ...]:
        return tuple(
            self._components[name].snapshot()
            for name in sorted(self._components)
        )

    def preload(self, names: Iterable[str]) -> tuple[str, ...]:
        loaded: list[str] = []
        for name in tuple(names):
            self.get(name).get()
            loaded.append(name)
        return tuple(loaded)


__all__ = [
    "LazyComponent",
    "LazyComponentRegistry",
    "LazyLoadError",
    "LazyProxy",
    "LazyRecursiveLoadError",
    "LazySnapshot",
    "LazyState",
]
