from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Pattern

from atlas.core.config import (
    AUTO_MEMORY_ALLOW_SENSITIVE,
    AUTO_MEMORY_ENABLED,
    AUTO_MEMORY_MIN_CONFIDENCE,
    USER_NAME,
)
from atlas.memory.database import MemoryStore
from atlas.memory.models import MemoryRecord


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    content: str
    category: str
    memory_key: str
    importance: float
    confidence: float


@dataclass(frozen=True, slots=True)
class AutoMemoryCaptureResult:
    candidates: tuple[MemoryCandidate, ...]
    records: tuple[MemoryRecord, ...]
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    ignored_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _ExtractionRule:
    pattern: Pattern[str]
    category: str
    importance: float
    confidence: float
    key_builder: Callable[[re.Match[str]], str]
    content_builder: Callable[[re.Match[str]], str]


class AutomaticMemoryExtractor:
    """Extrai apenas fatos explicitamente declarados pelo usuário."""

    _SENSITIVE_PATTERN = re.compile(
        r"\b(?:senha|password|token|cpf|cnpj|cvv|cart[aã]o|"
        r"conta banc[aá]ria|chave pix|c[oó]digo de seguran[cç]a|"
        r"diagn[oó]stico|doen[cç]a|medicamento|rem[eé]dio|"
        r"tratamento m[eé]dico|relig(?:i[aã]o|ioso)|"
        r"orienta[cç][aã]o sexual)\b",
        re.IGNORECASE,
    )
    _DENIAL_PATTERN = re.compile(
        r"\b(?:n[aã]o|nao)\s+(?:lembre|memorize|salve|guarde)\b|"
        r"\b(?:esque[cç]a|apague)\s+(?:isso|essa informa[cç][aã]o)\b",
        re.IGNORECASE,
    )
    _QUESTION_PATTERN = re.compile(
        r"^(?:quem|qual|quais|quando|onde|como|por que|porque|"
        r"ser[aá] que|voc[eê])\b",
        re.IGNORECASE,
    )
    _COMMAND_PATTERN = re.compile(
        r"^(?:abra|abre|abrir|acesse|clique|pesquise|procure|"
        r"busque|feche|inicie|execute|fa[cç]a|crie|envie|"
        r"lembre|memorize|esque[cç]a|apague|cancele)\b",
        re.IGNORECASE,
    )
    _END = (
        r"(?=\s+e\s+(?:eu\s+)?(?:moro|vivo|resido|trabalho|"
        r"estudo|fa[cç]o|gosto|prefiro|quero)\b|[,.!?;]|$)"
    )

    def __init__(
        self,
        *,
        user_name: str = USER_NAME,
        allow_sensitive: bool = AUTO_MEMORY_ALLOW_SENSITIVE,
        minimum_confidence: float = AUTO_MEMORY_MIN_CONFIDENCE,
    ) -> None:
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("A confiança mínima deve estar entre 0 e 1.")

        self.user_name = user_name.strip() or "O usuário"
        self.allow_sensitive = bool(allow_sensitive)
        self.minimum_confidence = float(minimum_confidence)
        self._rules = self._build_rules()

    def extract(self, text: str) -> list[MemoryCandidate]:
        normalized = " ".join(str(text).split()).strip()
        normalized = re.sub(
            r"^(?:atlas|atras)\b[\s,;:!?.-]*",
            "",
            normalized,
            count=1,
            flags=re.IGNORECASE,
        )

        if not normalized or len(normalized) > 500:
            return []

        if "?" in normalized or self._QUESTION_PATTERN.match(normalized):
            return []

        if self._COMMAND_PATTERN.match(normalized):
            return []

        if self._DENIAL_PATTERN.search(normalized):
            return []

        if (
            not self.allow_sensitive
            and self._SENSITIVE_PATTERN.search(normalized)
        ):
            return []

        candidates: list[MemoryCandidate] = []
        seen_keys: set[str] = set()

        for rule in self._rules:
            if rule.confidence < self.minimum_confidence:
                continue

            for match in rule.pattern.finditer(normalized):
                key = rule.key_builder(match)

                if not key or key in seen_keys:
                    continue

                content = rule.content_builder(match).strip(" .")

                if not content:
                    continue

                seen_keys.add(key)
                candidates.append(
                    MemoryCandidate(
                        content=content,
                        category=rule.category,
                        memory_key=key,
                        importance=rule.importance,
                        confidence=rule.confidence,
                    )
                )

        return candidates

    def _build_rules(self) -> tuple[_ExtractionRule, ...]:
        name = self.user_name

        def value(match: re.Match[str]) -> str:
            return match.group("value").strip()

        return (
            _ExtractionRule(
                pattern=re.compile(
                    r"\b(?:meu nome [ée]|eu me chamo|pode me chamar de)\s+"
                    rf"(?P<value>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ '\-]{{1,60}}?){self._END}",
                    re.IGNORECASE,
                ),
                category="profile",
                importance=0.95,
                confidence=0.99,
                key_builder=lambda _: "profile.name",
                content_builder=lambda match: (
                    f"O nome do usuário é {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:eu\s+)?(?:moro|vivo|resido)\s+em\s+"
                    rf"(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="profile",
                importance=0.85,
                confidence=0.96,
                key_builder=lambda _: "profile.location",
                content_builder=lambda match: (
                    f"{name} mora em {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:eu\s+)?nasci\s+em\s+(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="profile",
                importance=0.75,
                confidence=0.94,
                key_builder=lambda _: "profile.birthplace",
                content_builder=lambda match: (
                    f"{name} nasceu em {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    r"\b(?:eu\s+)?tenho\s+(?P<value>\d{1,3})\s+anos\b",
                    re.IGNORECASE,
                ),
                category="profile",
                importance=0.65,
                confidence=0.97,
                key_builder=lambda _: "profile.age",
                content_builder=lambda match: (
                    f"{name} tem {value(match)} anos"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:eu\s+)?trabalho\s+(?:como|de)\s+"
                    rf"(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="work",
                importance=0.80,
                confidence=0.94,
                key_builder=lambda _: "work.role",
                content_builder=lambda match: (
                    f"{name} trabalha como {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:eu\s+)?trabalho\s+(?:na|no|em)\s+"
                    rf"(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="work",
                importance=0.75,
                confidence=0.92,
                key_builder=lambda _: "work.company",
                content_builder=lambda match: (
                    f"{name} trabalha em {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:eu\s+)?(?:estudo|curso)\s+"
                    rf"(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="education",
                importance=0.80,
                confidence=0.91,
                key_builder=lambda match: (
                    f"education:{self._slug(value(match))}"
                ),
                content_builder=lambda match: (
                    f"{name} estuda {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:eu\s+)?fa[cç]o\s+(?:faculdade|curso|gradua[cç][aã]o)"
                    rf"(?:\s+(?:de|em))?\s+(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="education",
                importance=0.85,
                confidence=0.96,
                key_builder=lambda match: (
                    f"education:{self._slug(value(match))}"
                ),
                content_builder=lambda match: (
                    f"{name} cursa {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:meu projeto (?:se chama|[ée])|"
                    rf"estou (?:criando|desenvolvendo) (?:o projeto )?)\s*"
                    rf"(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="project",
                importance=0.90,
                confidence=0.94,
                key_builder=lambda _: "project.current",
                content_builder=lambda match: (
                    f"O projeto atual de {name} é {value(match)}"
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\b(?:eu\s+)?(?P<verb>gosto muito de|gosto de|adoro|amo|"
                    rf"prefiro|n[aã]o gosto de|detesto|odeio)\s+"
                    rf"(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="preference",
                importance=0.70,
                confidence=0.90,
                key_builder=lambda match: (
                    f"preference:{self._slug(value(match))}"
                ),
                content_builder=lambda match: self._preference_content(
                    name,
                    match.group("verb"),
                    value(match),
                ),
            ),
            _ExtractionRule(
                pattern=re.compile(
                    rf"\bmeu objetivo [ée]\s+"
                    rf"(?P<value>.+?){self._END}",
                    re.IGNORECASE,
                ),
                category="goal",
                importance=0.80,
                confidence=0.84,
                key_builder=lambda match: (
                    f"goal:{self._slug(value(match))}"
                ),
                content_builder=lambda match: (
                    f"Um objetivo de {name} é {value(match)}"
                ),
            ),
        )

    @classmethod
    def _slug(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        without_accents = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        ).lower()
        words = re.findall(r"[a-z0-9]+", without_accents)
        ignored = {"a", "as", "o", "os", "de", "da", "do", "das", "dos"}
        useful = [word for word in words if word not in ignored]
        return "-".join(useful[:12])[:80]

    @staticmethod
    def _preference_content(name: str, verb: str, value: str) -> str:
        normalized_verb = unicodedata.normalize("NFKD", verb)
        normalized_verb = "".join(
            character
            for character in normalized_verb
            if not unicodedata.combining(character)
        ).lower()

        if normalized_verb in {"nao gosto de", "detesto", "odeio"}:
            return f"{name} não gosta de {value}"

        if normalized_verb == "prefiro":
            return f"{name} prefere {value}"

        return f"{name} gosta de {value}"


class AutoMemoryManager:
    """Persiste candidatos automáticos sem criar memórias duplicadas."""

    def __init__(
        self,
        memory: MemoryStore,
        *,
        extractor: AutomaticMemoryExtractor | None = None,
        enabled: bool = AUTO_MEMORY_ENABLED,
    ) -> None:
        self.memory = memory
        self.extractor = extractor or AutomaticMemoryExtractor()
        self.enabled = bool(enabled)

    def capture(self, user_text: str) -> AutoMemoryCaptureResult:
        if not self.enabled:
            return AutoMemoryCaptureResult(
                candidates=(),
                records=(),
                ignored_reason="disabled",
            )

        candidates = tuple(self.extractor.extract(user_text))

        if not candidates:
            return AutoMemoryCaptureResult(
                candidates=(),
                records=(),
                ignored_reason="no_candidate",
            )

        records: list[MemoryRecord] = []
        counters = {"created": 0, "updated": 0, "unchanged": 0}

        for candidate in candidates:
            record, action = self.memory.upsert_keyed_record(
                candidate.content,
                memory_key=candidate.memory_key,
                category=candidate.category,
                source="auto_capture",
                importance=candidate.importance,
            )
            records.append(record)
            counters[action] += 1

        return AutoMemoryCaptureResult(
            candidates=candidates,
            records=tuple(records),
            created=counters["created"],
            updated=counters["updated"],
            unchanged=counters["unchanged"],
        )
