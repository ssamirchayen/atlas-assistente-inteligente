from __future__ import annotations

import os
from pathlib import Path
import re

from dotenv import load_dotenv

from atlas.core.paths import resolve_runtime_paths

RUNTIME_PATHS = resolve_runtime_paths(module_file=__file__)
ROOT_DIR = RUNTIME_PATHS.install_root
load_dotenv(RUNTIME_PATHS.config_file)

PROJECT_DIR = Path(
    os.getenv("ATLAS_PROJECT_DIR", str(ROOT_DIR))
).expanduser().resolve()

DATA_DIR = RUNTIME_PATHS.data_dir
LOG_DIR = RUNTIME_PATHS.log_dir
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

ATLAS_NAME = os.getenv("ATLAS_NAME", "Atlas")
USER_NAME = os.getenv("ATLAS_USER", "Ssamir")
OLLAMA_MODEL = os.getenv("ATLAS_MODEL", "atlas")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")

# Atlas Core 1.0 — perfil global de execução. Valores inválidos retornam ao
# modo automático para evitar inicialização com uma configuração desconhecida.
ATLAS_RUNTIME_PROFILE = os.getenv(
    "ATLAS_RUNTIME_PROFILE",
    "auto",
).strip().lower()
if ATLAS_RUNTIME_PROFILE not in {"auto", "lite", "standard", "full"}:
    ATLAS_RUNTIME_PROFILE = "auto"


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


_OLLAMA_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]{0,127}$")


def _env_model(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value if _OLLAMA_MODEL_NAME.fullmatch(value) else default


# Atlas Core 1.0 — Model Router. Por padrão todos os perfis mantêm o modelo
# atual; modelos diferentes só entram após configuração explícita no .env.
OLLAMA_MODEL_LITE = _env_model("ATLAS_MODEL_LITE", OLLAMA_MODEL)
OLLAMA_MODEL_STANDARD = _env_model("ATLAS_MODEL_STANDARD", OLLAMA_MODEL)
OLLAMA_MODEL_FULL = _env_model("ATLAS_MODEL_FULL", OLLAMA_MODEL)
OLLAMA_TAGS_URL = os.getenv(
    "OLLAMA_TAGS_URL",
    "http://localhost:11434/api/tags",
).strip()
OLLAMA_INVENTORY_TIMEOUT = _env_float(
    "ATLAS_MODEL_INVENTORY_TIMEOUT",
    2.0,
    minimum=0.1,
    maximum=10.0,
)

# O executável usa o Edge já presente no Windows e evita baixar um navegador
# adicional. No modo fonte, a instalação atual do Chromium continua igual.
BROWSER_CHANNEL = os.getenv(
    "ATLAS_BROWSER_CHANNEL",
    "msedge" if RUNTIME_PATHS.frozen else "",
).strip().lower()
if BROWSER_CHANNEL not in {"", "msedge", "chrome"}:
    BROWSER_CHANNEL = ""


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

API_HOST = "127.0.0.1"
API_PORT = min(
    _env_int("ATLAS_API_PORT", 8765, minimum=1),
    65535,
)
API_ADMIN_KEY = os.getenv("ATLAS_API_KEY", "").strip()
API_READ_KEY = os.getenv("ATLAS_API_READ_KEY", "").strip()
API_COMMAND_TIMEOUT = _env_float(
    "ATLAS_API_COMMAND_TIMEOUT",
    120.0,
    minimum=1.0,
    maximum=3600.0,
)
API_AUDIT_DB = DATA_DIR / "api_audit.db"
API_AUDIT_RETENTION_DAYS = _env_int(
    "ATLAS_API_AUDIT_RETENTION_DAYS",
    90,
    minimum=1,
)
API_AUDIT_MAX_EVENTS = _env_int(
    "ATLAS_API_AUDIT_MAX_EVENTS",
    10000,
    minimum=100,
)

INTERNET_SEARCH_ENABLED = _env_bool("ATLAS_INTERNET_SEARCH", True)
INTERNET_SEARCH_TIMEOUT = _env_float(
    "ATLAS_INTERNET_SEARCH_TIMEOUT",
    8.0,
    minimum=1.0,
    maximum=30.0,
)
INTERNET_SEARCH_MAX_PER_DOMAIN = _env_int(
    "ATLAS_INTERNET_SEARCH_MAX_PER_DOMAIN",
    2,
    minimum=1,
)
INTERNET_SEARCH_RATE_LIMIT = _env_int(
    "ATLAS_INTERNET_SEARCH_RATE_LIMIT",
    30,
    minimum=1,
)
BRAVE_SEARCH_API_KEY = os.getenv("ATLAS_BRAVE_SEARCH_API_KEY", "").strip()
SEARXNG_URL = os.getenv("ATLAS_SEARXNG_URL", "").strip()
SEARXNG_ALLOW_PRIVATE = _env_bool(
    "ATLAS_SEARXNG_ALLOW_PRIVATE",
    False,
)

# Piloto escolar e WhatsApp Business Platform (Sprint 22, Etapa 3).
# O modo simulado permanece ativo até a configuração explícita da escola.
WHATSAPP_DRY_RUN = _env_bool("ATLAS_WHATSAPP_DRY_RUN", True)
WHATSAPP_ACCESS_TOKEN = os.getenv(
    "ATLAS_WHATSAPP_ACCESS_TOKEN",
    "",
).strip()
WHATSAPP_GRAPH_API_VERSION = os.getenv(
    "ATLAS_WHATSAPP_GRAPH_API_VERSION",
    "v26.0",
).strip()
WHATSAPP_TIMEOUT = _env_float(
    "ATLAS_WHATSAPP_TIMEOUT",
    15.0,
    minimum=1.0,
    maximum=60.0,
)
WHATSAPP_MAX_BATCH_SIZE = min(
    _env_int("ATLAS_WHATSAPP_MAX_BATCH_SIZE", 20, minimum=1),
    20,
)
WHATSAPP_OPERATIONS_PER_MINUTE = _env_int(
    "ATLAS_WHATSAPP_OPERATIONS_PER_MINUTE",
    20,
    minimum=1,
)

# Provisionamento corporativo de computadores (Sprint 22, Etapa 4).
# A execução real é uma opção explícita; o padrão apenas simula o plano.
PROVISIONING_DRY_RUN = _env_bool("ATLAS_PROVISIONING_DRY_RUN", True)
PROVISIONING_WORKSPACE = Path(
    os.getenv(
        "ATLAS_PROVISIONING_WORKSPACE",
        str(Path.home() / "Atlas_Workspace"),
    )
).expanduser().resolve()
PROVISIONING_COMMAND_TIMEOUT = _env_float(
    "ATLAS_PROVISIONING_COMMAND_TIMEOUT",
    900.0,
    minimum=10.0,
    maximum=3600.0,
)
PROVISIONING_MAX_STEPS = min(
    _env_int("ATLAS_PROVISIONING_MAX_STEPS", 25, minimum=1),
    50,
)

# Atlas Edge — execução real exige duas liberações explícitas no .env.
EDGE_EXECUTION_ENABLED = _env_bool("ATLAS_EDGE_EXECUTION_ENABLED", False)
EDGE_MAX_TASKS = min(
    _env_int("ATLAS_EDGE_MAX_TASKS", 50, minimum=1),
    100,
)
EDGE_AUDIT_RETENTION_DAYS = min(
    _env_int("ATLAS_EDGE_AUDIT_RETENTION_DAYS", 90, minimum=1),
    3650,
)
EDGE_AUDIT_MAX_EVENTS = min(
    _env_int("ATLAS_EDGE_AUDIT_MAX_EVENTS", 10_000, minimum=100),
    100_000,
)
EDGE_MAX_ONBOARDINGS = min(
    _env_int("ATLAS_EDGE_MAX_ONBOARDINGS", 200, minimum=10),
    1000,
)
EDGE_MAX_ACTIVE_ONBOARDINGS = min(
    _env_int("ATLAS_EDGE_MAX_ACTIVE_ONBOARDINGS", 20, minimum=1),
    100,
)

SESSION_DB = DATA_DIR / "operational_sessions.db"
SESSION_FILE = DATA_DIR / "last_session.json"


# Atlas Vision — fundação visual.
# Capturas são locais e transitórias por padrão.
VISION_ENABLED = _env_bool("ATLAS_VISION", True)
VISION_CAPTURE_DIR = Path(
    os.getenv(
        "ATLAS_VISION_CAPTURE_DIR",
        str(DATA_DIR / "vision"),
    )
).expanduser().resolve()
VISION_KEEP_CAPTURES = _env_bool("ATLAS_VISION_KEEP_CAPTURES", False)

VISION_MODEL = os.getenv(
    "ATLAS_VISION_MODEL",
    "qwen2.5vl:3b",
).strip()
VISION_TIMEOUT = _env_float(
    "ATLAS_VISION_TIMEOUT",
    120.0,
    minimum=5.0,
    maximum=600.0,
)


MIC_ENABLED = os.getenv("ATLAS_MIC", "1") == "1"
VOICE_ENABLED = os.getenv("ATLAS_VOICE", "1") == "1"
WAKE_WORD_ENABLED = os.getenv("ATLAS_WAKE_WORD", "1") == "1"
TTS_PROVIDER = os.getenv("ATLAS_TTS_PROVIDER", "edge").strip().lower()
VOICE_PROFILE = os.getenv("ATLAS_VOICE_PROFILE", "balanced").strip().lower()
TTS_VOICE = os.getenv("ATLAS_TTS_VOICE", "pt-BR-AntonioNeural").strip()
TTS_RATE = os.getenv("ATLAS_TTS_RATE", "+0%").strip()
TTS_VOLUME = os.getenv("ATLAS_TTS_VOLUME", "+0%").strip()
TTS_PITCH = os.getenv("ATLAS_TTS_PITCH", "+0Hz").strip()
TTS_CACHE_ENABLED = _env_bool("ATLAS_TTS_CACHE", True)
TTS_CACHE_MAX_ENTRIES = _env_int(
    "ATLAS_TTS_CACHE_MAX_ENTRIES",
    64,
    minimum=1,
)
TTS_CHUNK_MAX_CHARS = _env_int(
    "ATLAS_TTS_CHUNK_MAX_CHARS",
    260,
    minimum=80,
)

TTS_PREFETCH_ENABLED = _env_bool(
    "ATLAS_TTS_PREFETCH",
    True,
)
TTS_PREFETCH_WORKERS = min(
    _env_int(
        "ATLAS_TTS_PREFETCH_WORKERS",
        1,
        minimum=1,
    ),
    2,
)
TTS_SENTENCE_PAUSE_MS = min(
    _env_int(
        "ATLAS_TTS_SENTENCE_PAUSE_MS",
        90,
        minimum=0,
    ),
    500,
)

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
