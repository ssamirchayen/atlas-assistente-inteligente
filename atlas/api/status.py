"""Coleta leve de estado para a API local."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from time import monotonic

import psutil

from atlas.api.models import (
    CapabilityStatus,
    HealthResponse,
    ResourceUsage,
    StatusResponse,
    VersionResponse,
)
from atlas.core.config import (
    ATLAS_NAME,
    MIC_ENABLED,
    VOICE_ENABLED,
    WAKE_WORD_ENABLED,
)
from atlas.version import API_VERSION, ATLAS_VERSION

ResourceReader = Callable[[], ResourceUsage]
Clock = Callable[[], datetime]
MonotonicClock = Callable[[], float]

SPECIALIZED_AGENTS = (
    "browser",
    "coding",
    "desktop",
    "sales",
    "helpdesk",
    "hr",
)


def read_resource_usage() -> ResourceUsage:
    """Lê somente percentuais, sem expor processos ou caminhos locais."""

    return ResourceUsage(
        cpu_percent=float(psutil.cpu_percent(interval=None)),
        memory_percent=float(psutil.virtual_memory().percent),
    )


class AtlasStatusService:
    """Produz respostas de observabilidade sem iniciar o AtlasKernel."""

    def __init__(
        self,
        *,
        resource_reader: ResourceReader = read_resource_usage,
        clock: Clock | None = None,
        monotonic_clock: MonotonicClock = monotonic,
    ) -> None:
        self._resource_reader = resource_reader
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic_clock = monotonic_clock
        self._started_at = monotonic_clock()

    def health(self) -> HealthResponse:
        return HealthResponse(timestamp=self._clock())

    def version(self) -> VersionResponse:
        return VersionResponse(
            name=ATLAS_NAME,
            version=ATLAS_VERSION,
            api_version=API_VERSION,
        )

    def status(self) -> StatusResponse:
        elapsed = max(0.0, self._monotonic_clock() - self._started_at)

        return StatusResponse(
            name=ATLAS_NAME,
            version=ATLAS_VERSION,
            api_version=API_VERSION,
            uptime_seconds=round(elapsed, 3),
            resources=self._resource_reader(),
            capabilities=CapabilityStatus(
                voice=VOICE_ENABLED,
                microphone=MIC_ENABLED,
                wake_word=WAKE_WORD_ENABLED,
                specialized_agents=SPECIALIZED_AGENTS,
            ),
        )
