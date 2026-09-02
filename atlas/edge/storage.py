"""Atomic, bounded local state storage for Atlas Edge."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from uuid import uuid4

from atlas.edge.models import EdgePersistentState


class EdgeStateError(RuntimeError):
    """Raised when persistent state cannot be trusted."""


class EdgeStateStore:
    """Persist a tiny JSON document without credentials or machine names."""

    def __init__(self, path: Path, *, max_bytes: int = 64 * 1024) -> None:
        if max_bytes <= 0:
            raise ValueError("O limite do estado deve ser positivo.")
        self.path = Path(path)
        self.max_bytes = max_bytes
        self._lock = RLock()

    def load(self) -> EdgePersistentState | None:
        with self._lock:
            if not self.path.exists():
                return None
            try:
                if self.path.stat().st_size > self.max_bytes:
                    raise EdgeStateError("O estado Atlas Edge excedeu o limite.")
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise EdgeStateError("O estado Atlas Edge não é um objeto.")
                return EdgePersistentState.from_dict(payload)
            except EdgeStateError:
                raise
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise EdgeStateError(
                    "O estado Atlas Edge está ausente de integridade."
                ) from exc

    def save(self, state: EdgePersistentState) -> None:
        encoded = json.dumps(
            state.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > self.max_bytes:
            raise EdgeStateError("O estado Atlas Edge excedeu o limite.")

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(
                f".{self.path.name}.{uuid4().hex}.tmp"
            )
            try:
                with temporary.open("xb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    temporary.chmod(0o600)
                except OSError:
                    pass
                os.replace(temporary, self.path)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise EdgeStateError(
                    "Não foi possível persistir o estado Atlas Edge."
                ) from exc
