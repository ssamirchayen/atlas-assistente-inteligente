from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace

import pytest

from atlas.admin.service import AdminConsoleService, AdminHealth, AdminSnapshot
from atlas.core.lazy import LazyComponent, LazyComponentRegistry


class Summary:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def public_summary(self) -> dict[str, object]:
        return dict(self.values)


class FakeDecision:
    def public_summary(self) -> dict[str, object]:
        return {
            "task": "chat",
            "profile": "standard",
            "model_name": "atlas",
            "context_limit": 8192,
        }


def kernel(
    *,
    pressure: str = "normal",
    support: str = "supported",
    profile_failure: bool = False,
    resource_failure: bool = False,
    audit_failure: bool = False,
):
    brain = LazyComponent("brain", lambda: SimpleNamespace(last_model_decision=None))
    vision = LazyComponent("vision", lambda: object())

    class Profile:
        def public_summary(self):
            if profile_failure:
                raise RuntimeError("segredo-do-perfil")
            return {
                "selected": "standard",
                "support_status": support,
                "fallback_applied": False,
            }

    class Resources:
        def status(self):
            if resource_failure:
                raise RuntimeError("segredo-dos-recursos")
            return Summary(
                {
                    "profile": "standard",
                    "support_status": support,
                    "pressure": pressure,
                    "active_leases": 0,
                    "capacity": 2,
                    "cpu_percent": 20.0,
                    "memory_percent": 40.0,
                    "available_memory_gb": 8.0,
                    "process_rss_mb": 200.0,
                }
            )

        def audit_events(self):
            if audit_failure:
                raise RuntimeError("segredo-da-auditoria")
            return (
                SimpleNamespace(action=SimpleNamespace(value="admitted")),
                SimpleNamespace(action=SimpleNamespace(value="released")),
                SimpleNamespace(action=SimpleNamespace(value="rejected")),
            )

    return SimpleNamespace(
        runtime_profile=Profile(),
        resource_manager=Resources(),
        lazy_components=LazyComponentRegistry((brain, vision)),
        _brain_component=brain,
    )


def test_healthy_snapshot_is_read_only_and_complete() -> None:
    snapshot = AdminConsoleService(kernel()).snapshot()
    assert snapshot.health is AdminHealth.HEALTHY
    assert snapshot.profile["selected"] == "standard"
    assert snapshot.resources["pressure"] == "normal"
    assert snapshot.capabilities["read_only"] is True
    assert snapshot.capabilities["mutating_controls"] is False
    assert snapshot.reason_codes == ("systems_healthy",)


def test_snapshot_does_not_load_lazy_components() -> None:
    current = kernel()
    snapshot = AdminConsoleService(current).snapshot()
    assert current._brain_component.loaded is False
    assert [item["state"] for item in snapshot.lazy_components] == [
        "unloaded",
        "unloaded",
    ]
    assert snapshot.model_route is None


def test_loaded_brain_exposes_only_public_model_decision() -> None:
    current = kernel()
    brain = current._brain_component.get()
    brain.last_model_decision = FakeDecision()
    snapshot = AdminConsoleService(current).snapshot()
    assert snapshot.model_route is not None
    assert snapshot.model_route["model_name"] == "atlas"
    assert "prompt" not in snapshot.model_route


@pytest.mark.parametrize(
    ("pressure", "expected"),
    [
        ("normal", AdminHealth.HEALTHY),
        ("warning", AdminHealth.ATTENTION),
        ("critical", AdminHealth.CRITICAL),
    ],
)
def test_pressure_controls_health(pressure: str, expected: AdminHealth) -> None:
    assert AdminConsoleService(kernel(pressure=pressure)).snapshot().health is expected


@pytest.mark.parametrize(
    ("support", "expected"),
    [
        ("supported", AdminHealth.HEALTHY),
        ("limited", AdminHealth.ATTENTION),
        ("unsupported", AdminHealth.CRITICAL),
    ],
)
def test_runtime_support_controls_health(support: str, expected: AdminHealth) -> None:
    assert AdminConsoleService(kernel(support=support)).snapshot().health is expected


def test_both_primary_sections_unavailable_set_unavailable_health() -> None:
    snapshot = AdminConsoleService(
        kernel(profile_failure=True, resource_failure=True)
    ).snapshot()
    assert snapshot.health is AdminHealth.UNAVAILABLE
    assert "profile_unavailable" in snapshot.reason_codes
    assert "resource_metrics_unavailable" in snapshot.reason_codes


@pytest.mark.parametrize(
    ("profile_failure", "resource_failure"),
    [(True, False), (False, True)],
)
def test_one_primary_failure_sets_attention(
    profile_failure: bool,
    resource_failure: bool,
) -> None:
    snapshot = AdminConsoleService(
        kernel(
            profile_failure=profile_failure,
            resource_failure=resource_failure,
        )
    ).snapshot()
    assert snapshot.health is AdminHealth.ATTENTION


def test_audit_is_aggregate_and_excludes_identifiers() -> None:
    audit = AdminConsoleService(kernel()).snapshot().resource_audit
    assert audit == {
        "available": True,
        "total_events": 3,
        "admitted": 1,
        "rejected": 1,
        "released": 1,
    }
    assert "lease_id" not in audit
    assert "event_id" not in audit


def test_audit_failure_is_sanitized() -> None:
    snapshot = AdminConsoleService(kernel(audit_failure=True)).snapshot()
    assert snapshot.resource_audit["available"] is False
    assert "segredo" not in repr(snapshot.public_summary())
    assert snapshot.health is AdminHealth.ATTENTION


@pytest.mark.parametrize(
    "failure",
    [
        {"profile_failure": True},
        {"resource_failure": True},
        {"audit_failure": True},
    ],
)
def test_internal_error_messages_never_reach_snapshot(failure) -> None:
    rendered = repr(AdminConsoleService(kernel(**failure)).snapshot().public_summary())
    assert "segredo" not in rendered


def test_snapshot_mappings_are_immutable() -> None:
    snapshot = AdminConsoleService(kernel()).snapshot()
    with pytest.raises(TypeError):
        snapshot.profile["selected"] = "full"  # type: ignore[index]
    with pytest.raises(TypeError):
        snapshot.capabilities["read_only"] = False  # type: ignore[index]


def test_public_summary_returns_detached_containers() -> None:
    snapshot = AdminConsoleService(kernel()).snapshot()
    public = snapshot.public_summary()
    public["profile"]["selected"] = "alterado"  # type: ignore[index]
    assert snapshot.profile["selected"] == "standard"


def test_clock_is_normalized_to_utc() -> None:
    instant = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
    snapshot = AdminConsoleService(kernel(), clock=lambda: instant).snapshot()
    assert snapshot.generated_at == instant
    assert snapshot.public_summary()["generated_at"].endswith("+00:00")


def test_failed_lazy_component_is_visible_without_exception_details() -> None:
    current = kernel()
    failing = LazyComponent(
        "optional",
        lambda: (_ for _ in ()).throw(RuntimeError("segredo-lazy")),
    )
    current.lazy_components = LazyComponentRegistry(
        (current._brain_component, failing)
    )
    with pytest.raises(Exception):
        failing.get()
    snapshot = AdminConsoleService(current).snapshot()
    failed = next(item for item in snapshot.lazy_components if item["name"] == "optional")
    assert failed["state"] == "failed"
    assert failed["last_error_type"] == "RuntimeError"
    assert "segredo-lazy" not in repr(snapshot.public_summary())


@pytest.mark.parametrize("field", ["profile", "resources", "resource_audit"])
def test_primary_sections_are_mapping_proxies(field: str) -> None:
    snapshot = AdminConsoleService(kernel()).snapshot()
    assert isinstance(getattr(snapshot, field), MappingProxyType)


def test_snapshot_requires_timezone() -> None:
    with pytest.raises(ValueError, match="fuso horário"):
        AdminSnapshot(
            generated_at=datetime(2026, 9, 3),
            health=AdminHealth.HEALTHY,
            profile={},
            resources={},
            lazy_components=(),
            model_route=None,
            resource_audit={},
            capabilities={},
            reason_codes=("ok",),
        )


@pytest.mark.parametrize("reasons", [(), ("x", "x")])
def test_snapshot_requires_unique_nonempty_reasons(reasons) -> None:
    with pytest.raises(ValueError, match="reason_codes"):
        AdminSnapshot(
            generated_at=datetime.now(timezone.utc),
            health=AdminHealth.HEALTHY,
            profile={},
            resources={},
            lazy_components=(),
            model_route=None,
            resource_audit={},
            capabilities={},
            reason_codes=reasons,
        )

