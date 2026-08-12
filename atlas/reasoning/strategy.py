from enum import Enum


class Strategy(str, Enum):
    DIRECT = "direct"

    MEMORY = "memory"

    PLANNER = "planner"

    LLM = "llm"

    ASK = "ask"