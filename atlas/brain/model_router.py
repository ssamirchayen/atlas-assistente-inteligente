"""Seleção local, previsível e observável de modelos do Ollama."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
import re
from threading import RLock
from typing import Any, Protocol

import requests

from atlas.core.resource_manager import ResourcePressure
from atlas.core.runtime_profile import RuntimeProfile, RuntimeProfileDecision


_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+-]{0,127}$")


class ModelTask(StrEnum):
    CHAT = "chat"
    PLANNING = "planning"
    CODING = "coding"
    ANALYSIS = "analysis"


class ModelTier(IntEnum):
    LITE = 1
    BALANCED = 2
    LARGE = 3


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    name: str
    tier: ModelTier
    min_total_ram_gb: float
    min_available_ram_gb: float
    context_limit: int
    min_vram_gb: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _MODEL_NAME.fullmatch(self.name):
            raise ValueError("Nome de modelo inválido.")
        if not isinstance(self.tier, ModelTier):
            raise TypeError("tier deve ser ModelTier.")
        for label in ("min_total_ram_gb", "min_available_ram_gb"):
            value = getattr(self, label)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{label} deve ser não negativo.")
        if self.min_vram_gb is not None and (
            not isinstance(self.min_vram_gb, (int, float))
            or isinstance(self.min_vram_gb, bool)
            or self.min_vram_gb < 0
        ):
            raise ValueError("min_vram_gb deve ser não negativo.")
        if (
            not isinstance(self.context_limit, int)
            or isinstance(self.context_limit, bool)
            or self.context_limit < 512
        ):
            raise ValueError("context_limit deve ser inteiro de pelo menos 512.")


@dataclass(frozen=True, slots=True)
class ModelRouteDecision:
    task: ModelTask
    profile: RuntimeProfile
    target_tier: ModelTier
    selected_tier: ModelTier
    model_name: str
    context_limit: int
    fallback_applied: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.profile is RuntimeProfile.AUTO:
            raise ValueError("A decisão exige um perfil concreto.")
        if not _MODEL_NAME.fullmatch(self.model_name):
            raise ValueError("A decisão contém modelo inválido.")
        if self.context_limit < 512:
            raise ValueError("context_limit inválido.")
        if not self.reason_codes or len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes deve ser único e não vazio.")

    def public_summary(self) -> dict[str, object]:
        return {
            "task": self.task.value,
            "profile": self.profile.value,
            "target_tier": self.target_tier.name.lower(),
            "selected_tier": self.selected_tier.name.lower(),
            "model_name": self.model_name,
            "context_limit": self.context_limit,
            "fallback_applied": self.fallback_applied,
            "reason_codes": self.reason_codes,
        }


class ModelInventory(Protocol):
    def available_models(self) -> frozenset[str] | None: ...


class ResourceStatusReader(Protocol):
    def status(self) -> Any: ...


class OllamaModelInventory:
    """Consulta somente nomes de modelos locais e mantém um cache em memória."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 2.0,
        getter: Callable[..., Any] | None = None,
    ) -> None:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValueError("URL do inventário Ollama inválida.")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout deve ser positivo.")
        self._url = url
        self._timeout = float(timeout)
        self._getter = getter or requests.get
        self._cached: frozenset[str] | None = None
        self._attempted = False
        self._lock = RLock()

    def available_models(self) -> frozenset[str] | None:
        with self._lock:
            if self._attempted:
                return self._cached
            self._attempted = True
            try:
                response = self._getter(self._url, timeout=self._timeout)
                response.raise_for_status()
                payload = response.json()
                models = payload.get("models", [])
                names = {
                    str(item.get("name") or item.get("model") or "").strip()
                    for item in models
                    if isinstance(item, dict)
                }
                self._cached = frozenset(
                    name for name in names if _MODEL_NAME.fullmatch(name)
                )
            except (requests.RequestException, AttributeError, TypeError, ValueError):
                self._cached = None
            return self._cached


class StaticModelInventory:
    def __init__(self, names: Iterable[str] | None) -> None:
        if names is None:
            self._names = None
            return
        parsed = frozenset(names)
        if any(not isinstance(name, str) or not _MODEL_NAME.fullmatch(name) for name in parsed):
            raise ValueError("Inventário contém nome de modelo inválido.")
        self._names = parsed

    def available_models(self) -> frozenset[str] | None:
        return self._names


class ModelRouter:
    def __init__(
        self,
        *,
        profile: RuntimeProfileDecision,
        candidates: Iterable[ModelCandidate],
        fallback_model: str,
        inventory: ModelInventory,
        resource_status: ResourceStatusReader | None = None,
    ) -> None:
        items = tuple(candidates)
        if not items:
            raise ValueError("O Model Router exige candidatos.")
        if not _MODEL_NAME.fullmatch(fallback_model):
            raise ValueError("fallback_model inválido.")
        self.profile = profile
        self._candidates = self._deduplicate(items)
        self._fallback_model = fallback_model
        self._inventory = inventory
        self._resource_status = resource_status
        self._last_decision: ModelRouteDecision | None = None
        self._lock = RLock()

    @property
    def last_decision(self) -> ModelRouteDecision | None:
        with self._lock:
            return self._last_decision

    def route(self, task: ModelTask | str) -> ModelRouteDecision:
        parsed_task = self._parse_task(task)
        reasons: list[str] = []
        target = self._target_tier(parsed_task)
        target, pressure_reason = self._apply_pressure(target)
        if pressure_reason:
            reasons.append(pressure_reason)

        available = self._inventory.available_models()
        if available is None:
            reasons.append("inventory_unavailable")

        eligible = [
            item
            for item in self._candidates
            if item.tier <= target
            and self._hardware_supports(item)
            and available is not None
            and self._is_available(item.name, available)
        ]
        if eligible:
            selected = max(eligible, key=lambda item: (item.tier, item.context_limit))
            reasons.append("best_supported_candidate")
        else:
            selected = self._fallback_candidate()
            reasons.append("configured_fallback_selected")

        context_limit = min(
            selected.context_limit,
            self.profile.budget.model_context_limit,
        )
        decision = ModelRouteDecision(
            task=parsed_task,
            profile=self.profile.selected,
            target_tier=target,
            selected_tier=selected.tier,
            model_name=selected.name,
            context_limit=context_limit,
            fallback_applied=(
                selected.name != self._preferred_name(target)
                or "inventory_unavailable" in reasons
            ),
            reason_codes=tuple(dict.fromkeys(reasons)),
        )
        with self._lock:
            self._last_decision = decision
        return decision

    def classify(self, text: str) -> ModelTask:
        normalized = text.casefold()
        if any(marker in normalized for marker in ("catálogo de ferramentas", "lista json", "planejador")):
            return ModelTask.PLANNING
        if any(marker in normalized for marker in (" código", "python", "javascript", "erro de programação", "debug")):
            return ModelTask.CODING
        if any(marker in normalized for marker in ("analise", "análise", "compare", "diagnóstico técnico")):
            return ModelTask.ANALYSIS
        return ModelTask.CHAT

    def _target_tier(self, task: ModelTask) -> ModelTier:
        if self.profile.selected is RuntimeProfile.LITE:
            return ModelTier.LITE
        if self.profile.selected is RuntimeProfile.STANDARD:
            return ModelTier.BALANCED
        if task in {ModelTask.CODING, ModelTask.ANALYSIS, ModelTask.PLANNING}:
            return ModelTier.LARGE
        return ModelTier.BALANCED

    def _apply_pressure(self, target: ModelTier) -> tuple[ModelTier, str | None]:
        if self._resource_status is None:
            return target, None
        try:
            pressure = self._resource_status.status().pressure
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return target, "resource_status_unavailable"
        if pressure is ResourcePressure.CRITICAL:
            return ModelTier.LITE, "critical_pressure_reduced_tier"
        if pressure is ResourcePressure.WARNING and target is ModelTier.LARGE:
            return ModelTier.BALANCED, "warning_pressure_reduced_tier"
        return target, None

    def _hardware_supports(self, candidate: ModelCandidate) -> bool:
        snapshot = self.profile.snapshot
        if snapshot.total_memory_gb < candidate.min_total_ram_gb:
            return False
        if snapshot.available_memory_gb < candidate.min_available_ram_gb:
            return False
        return not (
            candidate.min_vram_gb is not None
            and snapshot.gpu_vram_gb is not None
            and snapshot.gpu_vram_gb < candidate.min_vram_gb
        )

    def _preferred_name(self, tier: ModelTier) -> str:
        matches = [item for item in self._candidates if item.tier is tier]
        return matches[-1].name if matches else self._fallback_model

    def _fallback_candidate(self) -> ModelCandidate:
        matches = [item for item in self._candidates if item.name == self._fallback_model]
        if matches:
            return min(matches, key=lambda item: item.tier)
        return ModelCandidate(
            name=self._fallback_model,
            tier=ModelTier.LITE,
            min_total_ram_gb=0,
            min_available_ram_gb=0,
            context_limit=self.profile.budget.model_context_limit,
        )

    @staticmethod
    def _is_available(name: str, available: frozenset[str]) -> bool:
        return name in available or f"{name}:latest" in available

    @staticmethod
    def _parse_task(task: ModelTask | str) -> ModelTask:
        if isinstance(task, ModelTask):
            return task
        if not isinstance(task, str):
            raise TypeError("task deve ser texto ou ModelTask.")
        try:
            return ModelTask(task.strip().lower())
        except ValueError as exc:
            raise ValueError("Tarefa de modelo inválida.") from exc

    @staticmethod
    def _deduplicate(items: tuple[ModelCandidate, ...]) -> tuple[ModelCandidate, ...]:
        by_key: dict[tuple[str, ModelTier], ModelCandidate] = {}
        for item in items:
            by_key[(item.name, item.tier)] = item
        return tuple(by_key.values())


def create_default_model_router(
    profile: RuntimeProfileDecision,
    resource_status: ResourceStatusReader,
) -> ModelRouter:
    from atlas.core.config import (
        OLLAMA_INVENTORY_TIMEOUT,
        OLLAMA_MODEL,
        OLLAMA_MODEL_FULL,
        OLLAMA_MODEL_LITE,
        OLLAMA_MODEL_STANDARD,
        OLLAMA_TAGS_URL,
    )

    candidates = (
        ModelCandidate(
            name=OLLAMA_MODEL_LITE,
            tier=ModelTier.LITE,
            min_total_ram_gb=7.0,
            min_available_ram_gb=1.0,
            context_limit=4096,
        ),
        ModelCandidate(
            name=OLLAMA_MODEL_STANDARD,
            tier=ModelTier.BALANCED,
            min_total_ram_gb=14.0,
            min_available_ram_gb=2.5,
            context_limit=8192,
        ),
        ModelCandidate(
            name=OLLAMA_MODEL_FULL,
            tier=ModelTier.LARGE,
            min_total_ram_gb=28.0,
            min_available_ram_gb=6.0,
            min_vram_gb=8.0,
            context_limit=16384,
        ),
    )
    return ModelRouter(
        profile=profile,
        candidates=candidates,
        fallback_model=OLLAMA_MODEL,
        inventory=OllamaModelInventory(
            OLLAMA_TAGS_URL,
            timeout=OLLAMA_INVENTORY_TIMEOUT,
        ),
        resource_status=resource_status,
    )


__all__ = [
    "ModelCandidate",
    "ModelInventory",
    "ModelRouteDecision",
    "ModelRouter",
    "ModelTask",
    "ModelTier",
    "OllamaModelInventory",
    "StaticModelInventory",
    "create_default_model_router",
]
