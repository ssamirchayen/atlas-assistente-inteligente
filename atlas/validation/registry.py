"""Scenario discovery for the Atlas Validation Lab."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ScenarioDefinition


class ScenarioRegistry:
    """Load declarative scenarios from JSON files."""

    def __init__(self, scenarios_dir: Path) -> None:
        self.scenarios_dir = Path(scenarios_dir)

    def load(self) -> list[ScenarioDefinition]:
        scenarios: list[ScenarioDefinition] = []
        if not self.scenarios_dir.exists():
            return scenarios

        for path in sorted(self.scenarios_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError(f"Scenario file must contain a JSON list: {path}")
            scenarios.extend(ScenarioDefinition.from_dict(item) for item in payload)

        self._ensure_unique_ids(scenarios)
        return scenarios

    @staticmethod
    def _ensure_unique_ids(scenarios: list[ScenarioDefinition]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for scenario in scenarios:
            if scenario.scenario_id in seen:
                duplicates.add(scenario.scenario_id)
            seen.add(scenario.scenario_id)
        if duplicates:
            values = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate scenario id(s): {values}")
