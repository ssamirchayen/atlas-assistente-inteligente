from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    CHAT = "chat"

    OPEN = "open"

    SEARCH = "search"

    FILE = "file"

    WINDOW = "window"

    CODE = "code"

    SYSTEM = "system"

    QUESTION = "question"

    UNKNOWN = "unknown"