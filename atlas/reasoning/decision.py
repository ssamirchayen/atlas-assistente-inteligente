from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DecisionType(str, Enum):
    EXECUTE = "execute"
    ASK = "ask"
    PLAN = "plan"
    SEARCH_MEMORY = "search_memory"
    SEARCH_BROWSER = "search_browser"
    CHAT = "chat"
    REJECT = "reject"


@dataclass(slots=True)
class Decision:
    type: DecisionType
    reason: str = ""
    message: str = ""