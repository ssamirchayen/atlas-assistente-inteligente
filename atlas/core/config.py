from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

PROJECT_DIR = Path(
    os.getenv("ATLAS_PROJECT_DIR", str(ROOT_DIR))
).expanduser().resolve()

DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

ATLAS_NAME = os.getenv("ATLAS_NAME", "Atlas")
USER_NAME = os.getenv("ATLAS_USER", "Ssamir")
OLLAMA_MODEL = os.getenv("ATLAS_MODEL", "atlas")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float | None = None,
) -> float:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        parsed = float(value)
    except ValueError:
        return default

    if parsed < minimum:
        return default

    if maximum is not None and parsed > maximum:
        return default

    return parsed


def _env_int(name: str, default: int, *, minimum: int) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        parsed = int(value)
    except ValueError:
        return default

    return parsed if parsed >= minimum else default


EMBEDDINGS_ENABLED = _env_bool("ATLAS_EMBEDDINGS", True)
OLLAMA_EMBEDDING_MODEL = os.getenv(
    "ATLAS_EMBEDDING_MODEL",
    "qwen3-embedding:0.6b",
).strip()
OLLAMA_EMBEDDING_URL = os.getenv(
    "OLLAMA_EMBEDDING_URL",
    "http://localhost:11434/api/embed",
).strip()
OLLAMA_EMBEDDING_TIMEOUT = _env_float(
    "ATLAS_EMBEDDING_TIMEOUT",
    30.0,
    minimum=0.1,
)
OLLAMA_EMBEDDING_CACHE_SIZE = _env_int(
    "ATLAS_EMBEDDING_CACHE_SIZE",
    256,
    minimum=0,
)
MEMORY_SEMANTIC_MIN_SCORE = _env_float(
    "ATLAS_MEMORY_SEMANTIC_MIN_SCORE",
    0.25,
    minimum=0.0,
    maximum=1.0,
)
MEMORY_SEMANTIC_CANDIDATES = _env_int(
    "ATLAS_MEMORY_SEMANTIC_CANDIDATES",
    500,
    minimum=1,
)
AUTO_MEMORY_ENABLED = _env_bool("ATLAS_AUTO_MEMORY", True)
AUTO_MEMORY_ALLOW_SENSITIVE = _env_bool(
    "ATLAS_AUTO_MEMORY_ALLOW_SENSITIVE",
    False,
)
AUTO_MEMORY_MIN_CONFIDENCE = _env_float(
    "ATLAS_AUTO_MEMORY_MIN_CONFIDENCE",
    0.75,
    minimum=0.0,
    maximum=1.0,
)
MEMORY_DECAY_ENABLED = _env_bool("ATLAS_MEMORY_DECAY", True)
MEMORY_DECAY_HALF_LIFE_DAYS = _env_float(
    "ATLAS_MEMORY_DECAY_HALF_LIFE_DAYS",
    365.0,
    minimum=1.0,
)
MEMORY_DECAY_FLOOR = _env_float(
    "ATLAS_MEMORY_DECAY_FLOOR",
    0.20,
    minimum=0.0,
    maximum=1.0,
)
MEMORY_CONSOLIDATION_THRESHOLD = _env_float(
    "ATLAS_MEMORY_CONSOLIDATION_THRESHOLD",
    0.90,
    minimum=0.5,
    maximum=1.0,
)

MIC_ENABLED = os.getenv("ATLAS_MIC", "1") == "1"
VOICE_ENABLED = os.getenv("ATLAS_VOICE", "1") == "1"
WAKE_WORD_ENABLED = os.getenv("ATLAS_WAKE_WORD", "1") == "1"
TTS_PROVIDER = os.getenv("ATLAS_TTS_PROVIDER", "edge").strip().lower()
TTS_VOICE = os.getenv("ATLAS_TTS_VOICE", "pt-BR-AntonioNeural").strip()
TTS_RATE = os.getenv("ATLAS_TTS_RATE", "+0%").strip()
TTS_VOLUME = os.getenv("ATLAS_TTS_VOLUME", "+0%").strip()
TTS_PITCH = os.getenv("ATLAS_TTS_PITCH", "+0Hz").strip()

MEMORY_DB = DATA_DIR / "memory.db"
LOG_FILE = LOG_DIR / "atlas.log"

SYSTEM_PROMPT = f"""
Você é {ATLAS_NAME}, assistente pessoal local de {USER_NAME}.
Responda sempre em português brasileiro, com naturalidade, clareza e objetividade.
O programa possui síntese de voz externa; portanto, nunca diga que não pode falar ou produzir som.
O programa possui ferramentas locais controladas para abrir programas, sites e pastas.
Nunca diga que uma ação foi executada se o sistema não confirmar a execução.
Não invente memórias, arquivos, compromissos ou ações.
Não forneça comandos destrutivos sem contexto e confirmação.
Quando a pergunta for simples, responda brevemente.
"""
