from __future__ import annotations

from threading import Event, Lock, Thread

import pytest

from atlas.core.lazy import (
    LazyComponent,
    LazyComponentRegistry,
    LazyLoadError,
    LazyProxy,
    LazyState,
)


class DemoService:
    def __init__(self, value: str = "ready") -> None:
        self.value = value

    def respond(self, text: str) -> str:
        return f"{self.value}:{text}"


def test_factory_is_not_called_during_registration() -> None:
    calls = 0

    def factory() -> DemoService:
        nonlocal calls
        calls += 1
        return DemoService()

    component = LazyComponent("brain", factory)
    registry = LazyComponentRegistry((component,))

    assert calls == 0
    assert component.loaded is False
    assert component.peek() is None
    assert registry.snapshots()[0].state is LazyState.UNLOADED


def test_first_access_loads_and_reuses_same_instance() -> None:
    calls = 0

    def factory() -> DemoService:
        nonlocal calls
        calls += 1
        return DemoService()

    component = LazyComponent("brain", factory)

    first = component.get()
    second = component.get()

    assert first is second
    assert calls == 1
    assert component.peek() is first
    snapshot = component.snapshot()
    assert snapshot.state is LazyState.READY
    assert snapshot.load_attempts == 1
    assert snapshot.successful_loads == 1
    assert snapshot.load_duration_ms is not None


def test_concurrent_access_builds_exactly_once() -> None:
    calls = 0
    calls_lock = Lock()
    factory_started = Event()
    release_factory = Event()
    results: list[DemoService] = []

    def factory() -> DemoService:
        nonlocal calls
        with calls_lock:
            calls += 1
        factory_started.set()
        assert release_factory.wait(timeout=2)
        return DemoService()

    component = LazyComponent("vision", factory)
    threads = [Thread(target=lambda: results.append(component.get())) for _ in range(8)]
    for thread in threads:
        thread.start()
    assert factory_started.wait(timeout=2)
    release_factory.set()
    for thread in threads:
        thread.join(timeout=2)

    assert calls == 1
    assert len(results) == 8
    assert len({id(item) for item in results}) == 1


def test_failure_is_cached_without_leaking_message() -> None:
    calls = 0

    def factory() -> DemoService:
        nonlocal calls
        calls += 1
        raise RuntimeError("segredo-em-caminho-local")

    component = LazyComponent("brain", factory)

    with pytest.raises(LazyLoadError) as first:
        component.get()
    with pytest.raises(LazyLoadError) as second:
        component.get()

    assert calls == 1
    assert "segredo-em-caminho-local" not in str(first.value)
    assert second.value.error_type == "RuntimeError"
    snapshot = component.snapshot()
    assert snapshot.state is LazyState.FAILED
    assert snapshot.last_error_type == "RuntimeError"
    assert snapshot.successful_loads == 0


def test_explicit_failure_reset_allows_one_new_attempt() -> None:
    calls = 0

    def factory() -> DemoService:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporário")
        return DemoService()

    component = LazyComponent("brain", factory)

    with pytest.raises(LazyLoadError):
        component.get()
    assert component.reset_failure() is True
    assert component.get().value == "ready"
    assert component.reset_failure() is False
    assert calls == 2


def test_none_factory_result_is_a_cached_failure() -> None:
    component = LazyComponent("vision", lambda: None)

    with pytest.raises(LazyLoadError) as captured:
        component.get()

    assert captured.value.error_type == "TypeError"
    assert component.snapshot().state is LazyState.FAILED


def test_recursive_factory_fails_instead_of_deadlocking() -> None:
    holder = {}

    def factory() -> DemoService:
        return holder["component"].get()

    component = LazyComponent("brain", factory)
    holder["component"] = component

    with pytest.raises(LazyLoadError) as captured:
        component.get()

    assert captured.value.error_type == "LazyRecursiveLoadError"


def test_proxy_preserves_attribute_interface() -> None:
    component = LazyComponent("brain", lambda: DemoService("atlas"))
    proxy = LazyProxy(component)

    assert component.loaded is False
    assert proxy.respond("olá") == "atlas:olá"
    assert component.loaded is True
    assert proxy.unwrap() is component.get()


def test_proxy_for_callable_component() -> None:
    component = LazyComponent("callable", lambda: lambda value: value * 2)
    proxy = LazyProxy(component)

    assert proxy(3) == 6


def test_proxy_repr_and_bool_do_not_trigger_loading() -> None:
    component = LazyComponent("brain", lambda: DemoService())
    proxy = LazyProxy(component)

    assert bool(proxy) is True
    assert "unloaded" in repr(proxy)
    assert component.loaded is False


@pytest.mark.parametrize("name", ["", "A", "../brain", "brain secret", "a" * 65])
def test_component_rejects_unsafe_name(name: str) -> None:
    with pytest.raises(ValueError, match="Nome"):
        LazyComponent(name, DemoService)


def test_component_rejects_non_callable_factory() -> None:
    with pytest.raises(TypeError, match="factory"):
        LazyComponent("brain", object())  # type: ignore[arg-type]


def test_registry_rejects_empty_or_duplicate_components() -> None:
    with pytest.raises(ValueError, match="não pode ser vazio"):
        LazyComponentRegistry(())

    first = LazyComponent("brain", DemoService)
    duplicate = LazyComponent("brain", DemoService)
    with pytest.raises(ValueError, match="duplicados"):
        LazyComponentRegistry((first, duplicate))


def test_registry_reports_sorted_snapshots_without_loading() -> None:
    vision = LazyComponent("vision", DemoService)
    brain = LazyComponent("brain", DemoService)
    registry = LazyComponentRegistry((vision, brain))

    snapshots = registry.snapshots()

    assert [item.name for item in snapshots] == ["brain", "vision"]
    assert all(item.state is LazyState.UNLOADED for item in snapshots)


def test_registry_preloads_only_explicit_names() -> None:
    brain = LazyComponent("brain", DemoService)
    vision = LazyComponent("vision", DemoService)
    registry = LazyComponentRegistry((brain, vision))

    assert registry.preload(("brain",)) == ("brain",)
    assert brain.loaded is True
    assert vision.loaded is False


def test_registry_rejects_unknown_name() -> None:
    registry = LazyComponentRegistry((LazyComponent("brain", DemoService),))

    with pytest.raises(KeyError, match="desconhecido"):
        registry.get("vision")
