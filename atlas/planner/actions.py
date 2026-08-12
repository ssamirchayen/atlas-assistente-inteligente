from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"Action(type={self.type!r}, "
            f"parameters={self.parameters!r})"
        )