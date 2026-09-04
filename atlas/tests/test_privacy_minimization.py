from __future__ import annotations

import pytest

from atlas.privacy.minimization import DataMinimizer, Pseudonymizer


SECRET = b"atlas-test-privacy-secret-key-32-bytes-minimum"


def test_pseudonymizer_requires_strong_secret() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Pseudonymizer(b"short")


def test_pseudonym_is_deterministic_and_namespaced() -> None:
    pseudonymizer = Pseudonymizer(SECRET)
    first = pseudonymizer.pseudonymize("person-123", namespace="tenant-a:user")
    second = pseudonymizer.pseudonymize("person-123", namespace="tenant-a:user")
    other = pseudonymizer.pseudonymize("person-123", namespace="tenant-b:user")
    assert first == second
    assert first.startswith("psn_")
    assert other != first
    assert "person-123" not in first


@pytest.mark.parametrize(
    ("value", "namespace"),
    [("", "tenant-a:user"), ("person-123", "invalid namespace")],
)
def test_pseudonymizer_rejects_invalid_input(value: str, namespace: str) -> None:
    with pytest.raises(ValueError):
        Pseudonymizer(SECRET).pseudonymize(value, namespace=namespace)


def test_pseudonymizer_rejects_structured_value() -> None:
    with pytest.raises(TypeError, match="campo a campo"):
        Pseudonymizer(SECRET).pseudonymize(
            {"cpf": "123"},
            namespace="tenant-a:user",
        )


def test_minimizer_drops_undeclared_fields_and_preserves_order() -> None:
    result = DataMinimizer(Pseudonymizer(SECRET)).minimize(
        {"name": "Ada", "debug": "secret", "email": "ada@example.test"},
        allowed_fields=("email", "name"),
        namespace="tenant-a:profile",
    )
    assert dict(result.data) == {"email": "ada@example.test", "name": "Ada"}
    assert result.dropped_fields == ("debug",)


def test_minimizer_masks_and_pseudonymizes_declared_fields() -> None:
    result = DataMinimizer(Pseudonymizer(SECRET)).minimize(
        {"phone": "559299991234", "external_id": "lead-9", "name": "Ada"},
        allowed_fields=("phone", "external_id", "name"),
        masked_fields=("phone",),
        pseudonymized_fields=("external_id",),
        namespace="tenant-a:lead",
    )
    assert result.data["phone"] == "***1234"
    assert str(result.data["external_id"]).startswith("psn_")
    assert result.data["name"] == "Ada"
    assert result.protected_fields == ("external_id", "phone")


def test_minimization_result_repr_never_contains_values() -> None:
    result = DataMinimizer(Pseudonymizer(SECRET)).minimize(
        {"name": "highly-private-value"},
        allowed_fields=("name",),
        namespace="tenant-a:profile",
    )
    assert "highly-private-value" not in repr(result)
    with pytest.raises(TypeError):
        result.data["name"] = "changed"  # type: ignore[index]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allowed_fields": ("name", "name")},
        {"allowed_fields": ("name",), "masked_fields": ("email",)},
        {"allowed_fields": ("name",), "pseudonymized_fields": ("email",)},
        {
            "allowed_fields": ("name",),
            "masked_fields": ("name",),
            "pseudonymized_fields": ("name",),
        },
    ],
)
def test_minimizer_rejects_ambiguous_field_rules(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        DataMinimizer(Pseudonymizer(SECRET)).minimize(
            {"name": "Ada"},
            namespace="tenant-a:profile",
            **kwargs,
        )
