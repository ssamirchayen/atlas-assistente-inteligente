"""JSON suite discovery for Atlas Benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from .models import BenchmarkSuite


class BenchmarkCatalog:
    """Load and validate benchmark suites from a directory."""

    def __init__(self, suites_dir: Path) -> None:
        self.suites_dir = Path(suites_dir)

    def load(self) -> list[BenchmarkSuite]:
        if not self.suites_dir.exists():
            return []

        suites: list[BenchmarkSuite] = []
        for path in sorted(self.suites_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(
                    f"Benchmark suite file must contain a JSON object: {path}"
                )
            suites.append(BenchmarkSuite.from_dict(payload))

        self._ensure_unique_ids(suites)
        return suites

    def get(self, suite_id: str) -> BenchmarkSuite:
        for suite in self.load():
            if suite.suite_id == suite_id:
                return suite
        raise KeyError(f"Unknown benchmark suite: {suite_id}")

    @staticmethod
    def _ensure_unique_ids(suites: list[BenchmarkSuite]) -> None:
        ids = [suite.suite_id for suite in suites]
        duplicates = sorted({suite_id for suite_id in ids if ids.count(suite_id) > 1})
        if duplicates:
            raise ValueError(
                "Duplicate benchmark suite id(s): " + ", ".join(duplicates)
            )
