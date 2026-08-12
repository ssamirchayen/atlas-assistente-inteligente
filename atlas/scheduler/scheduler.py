from __future__ import annotations

from pathlib import Path

from .job import ScheduledJob
from .storage import SchedulerStorage


class Scheduler:

    def __init__(
        self,
        storage_path: Path | str | None = None,
    ) -> None:
        self.jobs: dict[str, ScheduledJob] = {}

        self.storage = (
            SchedulerStorage(storage_path)
            if storage_path is not None
            else SchedulerStorage()
        )

        self.load()

    def add_job(
        self,
        job: ScheduledJob,
    ) -> ScheduledJob:
        self.jobs[job.id] = job
        self.save()

        return job

    def remove_job(
        self,
        job_id: str,
    ) -> bool:
        removed_job = self.jobs.pop(
            job_id,
            None,
        )

        if removed_job is None:
            return False

        self.save()
        return True

    def get_job(
        self,
        job_id: str,
    ) -> ScheduledJob | None:
        return self.jobs.get(job_id)

    def all_jobs(
        self,
    ) -> list[ScheduledJob]:
        return list(self.jobs.values())

    def save(self) -> None:
        self.storage.save(
            self.all_jobs()
        )

    def load(self) -> None:
        loaded_jobs = self.storage.load()

        self.jobs = {
            job.id: job
            for job in loaded_jobs
        }

    @property
    def total(self) -> int:
        return len(self.jobs)

    @property
    def enabled_jobs(
        self,
    ) -> list[ScheduledJob]:
        return [
            job
            for job in self.jobs.values()
            if job.enabled
        ]