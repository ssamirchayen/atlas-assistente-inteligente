"""Atomic bounded persistence for employee onboarding workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Mapping

from atlas.edge.onboarding import EmployeeOnboarding


class EmployeeOnboardingStoreError(RuntimeError):
    """Fail-closed persistence error for onboarding state."""


class EmployeeOnboardingStore:
    def __init__(
        self,
        path: Path,
        *,
        max_records: int = 200,
        max_bytes: int = 1024 * 1024,
    ) -> None:
        if max_records <= 0 or max_bytes <= 0:
            raise ValueError("Os limites do onboarding devem ser positivos.")
        self.path = Path(path)
        self._max_records = max_records
        self._max_bytes = max_bytes
        self._lock = RLock()
        self._records = list(self._load())

    def list(self) -> tuple[EmployeeOnboarding, ...]:
        with self._lock:
            return tuple(self._records)

    def get(self, onboarding_id: str) -> EmployeeOnboarding | None:
        with self._lock:
            return next(
                (
                    record
                    for record in self._records
                    if record.onboarding_id == onboarding_id
                ),
                None,
            )

    def save(self, record: EmployeeOnboarding) -> EmployeeOnboarding:
        with self._lock:
            original = list(self._records)
            index = next(
                (
                    current
                    for current, item in enumerate(self._records)
                    if item.onboarding_id == record.onboarding_id
                ),
                None,
            )
            if index is None:
                self._prune_terminal()
                if len(self._records) >= self._max_records:
                    raise OverflowError(
                        "O histórico de onboardings atingiu o limite."
                    )
                self._records.append(record)
            else:
                current = self._records[index]
                if record.revision <= current.revision:
                    raise ValueError("A revisão do onboarding deve avançar.")
                self._records[index] = record
            try:
                self._write()
            except Exception:
                self._records = original
                raise
            return record

    def _load(self) -> tuple[EmployeeOnboarding, ...]:
        if not self.path.exists():
            return ()
        try:
            if self.path.stat().st_size > self._max_bytes:
                raise EmployeeOnboardingStoreError(
                    "O arquivo de onboardings excede o limite."
                )
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != 1:
                raise EmployeeOnboardingStoreError(
                    "O formato do histórico de onboardings não é suportado."
                )
            raw_records = payload.get("records")
            if not isinstance(raw_records, list):
                raise EmployeeOnboardingStoreError(
                    "A lista de onboardings é inválida."
                )
            records = tuple(
                EmployeeOnboarding.from_dict(_mapping(item))
                for item in raw_records
            )
            if len(records) > self._max_records:
                raise EmployeeOnboardingStoreError(
                    "O histórico de onboardings excede o limite."
                )
            if len({item.onboarding_id for item in records}) != len(records):
                raise EmployeeOnboardingStoreError(
                    "O histórico contém onboardings duplicados."
                )
            return records
        except EmployeeOnboardingStoreError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise EmployeeOnboardingStoreError(
                "O arquivo de onboardings está corrompido."
            ) from exc

    def _write(self) -> None:
        payload = {
            "schema_version": 1,
            "records": [item.as_dict() for item in self._records],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self._max_bytes:
            raise EmployeeOnboardingStoreError(
                "O histórico de onboardings excede o limite."
            )
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        except OSError as exc:
            raise EmployeeOnboardingStoreError(
                "Não foi possível salvar os onboardings."
            ) from exc

    def _prune_terminal(self) -> None:
        while len(self._records) >= self._max_records:
            index = next(
                (
                    current
                    for current, item in enumerate(self._records)
                    if item.terminal
                ),
                None,
            )
            if index is None:
                break
            self._records.pop(index)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("O onboarding persistido deve ser um objeto.")
    return value
