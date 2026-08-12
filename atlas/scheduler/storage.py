from __future__ import annotations

import json
from pathlib import Path

from .job import ScheduledJob

SCHEDULER_DATABASE = (
    Path("atlas_data")
    / "scheduler.json"
)


class SchedulerStorage:

    def __init__(
        self,
        database_path: Path | str = SCHEDULER_DATABASE,
    ) -> None:
        self.database_path = Path(database_path)

    def save(
        self,
        jobs: list[ScheduledJob],
    ) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.database_path.with_suffix(
            ".tmp"
        )

        data = [
            job.to_dict()
            for job in jobs
        ]

        temporary_path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.database_path
        )

    def load(self) -> list[ScheduledJob]:
        if not self.database_path.exists():
            return []

        try:
            raw_content = self.database_path.read_text(
                encoding="utf-8"
            )

            if not raw_content.strip():
                return []

            data = json.loads(raw_content)

        except (
            OSError,
            json.JSONDecodeError,
        ):
            return []

        if not isinstance(data, list):
            return []

        jobs: list[ScheduledJob] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            try:
                jobs.append(
                    ScheduledJob.from_dict(item)
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

        return jobs