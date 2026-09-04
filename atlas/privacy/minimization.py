"""Minimização, mascaramento e pseudonimização de dados autorizados."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping


_SAFE_FIELD = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_SAFE_NAMESPACE = re.compile(r"^[a-z][a-z0-9_.:-]{2,95}$")


def _unique_fields(label: str, values: Iterable[str]) -> tuple[str, ...]:
    fields = tuple(values)
    if len(fields) != len(set(fields)):
        raise ValueError(f"{label} não pode conter duplicidades.")
    if any(not isinstance(field, str) or not _SAFE_FIELD.fullmatch(field) for field in fields):
        raise ValueError(f"{label} contém um campo inválido.")
    return fields


class Pseudonymizer:
    """Produz pseudônimos HMAC estáveis sem armazenar identificadores brutos."""

    def __init__(self, secret: bytes) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("A chave de pseudonimização deve possuir ao menos 32 bytes.")
        self._secret = secret

    def pseudonymize(self, value: object, *, namespace: str) -> str:
        if not isinstance(namespace, str) or not _SAFE_NAMESPACE.fullmatch(namespace):
            raise ValueError("O namespace de pseudonimização é inválido.")
        if isinstance(value, (Mapping, list, tuple, set, frozenset)):
            raise TypeError("Estruturas devem ser minimizadas campo a campo.")
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("O valor de pseudonimização não pode ser vazio.")
        digest = hmac.new(
            self._secret,
            f"{namespace}\x00{normalized}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"psn_{digest}"


@dataclass(frozen=True, slots=True)
class DataMinimizationResult:
    """Resultado cujo repr omite deliberadamente os valores tratados."""

    data: Mapping[str, Any]
    dropped_fields: tuple[str, ...]
    protected_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))

    def __repr__(self) -> str:
        return (
            "DataMinimizationResult("
            f"field_count={len(self.data)}, "
            f"dropped_fields={self.dropped_fields!r}, "
            f"protected_fields={self.protected_fields!r})"
        )


class DataMinimizer:
    """Mantém apenas campos permitidos e aplica as proteções declaradas."""

    def __init__(self, pseudonymizer: Pseudonymizer) -> None:
        if not isinstance(pseudonymizer, Pseudonymizer):
            raise TypeError("pseudonymizer deve ser Pseudonymizer.")
        self._pseudonymizer = pseudonymizer

    def minimize(
        self,
        payload: Mapping[str, Any],
        *,
        allowed_fields: Iterable[str],
        masked_fields: Iterable[str] = (),
        pseudonymized_fields: Iterable[str] = (),
        namespace: str,
    ) -> DataMinimizationResult:
        if not isinstance(payload, Mapping):
            raise TypeError("payload deve ser um mapeamento.")
        allowed = _unique_fields("allowed_fields", allowed_fields)
        masked = _unique_fields("masked_fields", masked_fields)
        pseudonymized = _unique_fields(
            "pseudonymized_fields", pseudonymized_fields
        )
        allowed_set = set(allowed)
        if not set(masked).issubset(allowed_set):
            raise ValueError("masked_fields deve ser subconjunto de allowed_fields.")
        if not set(pseudonymized).issubset(allowed_set):
            raise ValueError(
                "pseudonymized_fields deve ser subconjunto de allowed_fields."
            )
        if set(masked) & set(pseudonymized):
            raise ValueError("Um campo não pode ser mascarado e pseudonimizado.")

        output: dict[str, Any] = {}
        for field in allowed:
            if field not in payload:
                continue
            value = payload[field]
            if field in pseudonymized:
                value = self._pseudonymizer.pseudonymize(
                    value,
                    namespace=f"{namespace}:{field}",
                )
            elif field in masked:
                value = self._mask(value)
            output[field] = value

        dropped = tuple(sorted(str(field) for field in payload if field not in allowed_set))
        protected = tuple(sorted(set(masked) | set(pseudonymized)))
        return DataMinimizationResult(
            data=output,
            dropped_fields=dropped,
            protected_fields=protected,
        )

    @staticmethod
    def _mask(value: object) -> str:
        normalized = str(value).strip()
        if not normalized:
            return "***"
        if len(normalized) <= 4:
            return "***"
        return f"***{normalized[-4:]}"
