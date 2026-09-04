"""Piloto somente leitura da Admin Console, sem abrir a GUI."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from atlas.admin.service import AdminConsoleService
from atlas.core.lazy import LazyComponent, LazyComponentRegistry


class Summary:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def public_summary(self) -> dict[str, object]:
        return dict(self._values)


def build_demo_kernel():
    brain = LazyComponent("brain", lambda: object())
    vision = LazyComponent("vision", lambda: object())
    profile = Summary(
        {
            "selected": "standard",
            "support_status": "supported",
            "fallback_applied": False,
        }
    )
    resources = SimpleNamespace(
        status=lambda: Summary(
            {
                "profile": "standard",
                "support_status": "supported",
                "pressure": "normal",
                "active_leases": 0,
                "capacity": 2,
                "cpu_percent": 18.0,
                "memory_percent": 42.0,
                "available_memory_gb": 8.7,
                "process_rss_mb": 210.0,
            }
        ),
        audit_events=lambda: (),
    )
    return SimpleNamespace(
        runtime_profile=profile,
        resource_manager=resources,
        lazy_components=LazyComponentRegistry((brain, vision)),
        _brain_component=brain,
    )


def main() -> None:
    kernel = build_demo_kernel()
    snapshot = AdminConsoleService(
        kernel,
        clock=lambda: datetime.now(timezone.utc),
    ).snapshot()
    print("Sprint 25 — Etapa 5: Admin Console")
    print(f"Saúde: {snapshot.health.value}")
    print(f"Perfil: {snapshot.profile['selected']}")
    print(f"Pressão: {snapshot.resources['pressure']}")
    print(
        "Lazy: "
        + ", ".join(
            f"{item['name']}={item['state']}"
            for item in snapshot.lazy_components
        )
    )
    print(f"Somente leitura: {snapshot.capabilities['read_only']}")
    assert kernel._brain_component.loaded is False
    print("Brain e Vision permaneceram descarregados; nenhuma ação foi executada.")


if __name__ == "__main__":
    main()

