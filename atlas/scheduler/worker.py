from __future__ import annotations

import calendar
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from .job import ScheduledJob
from .scheduler import Scheduler


class SchedulerWorker:
    """
    Verifica periodicamente os agendamentos e executa
    aqueles cujo horário já chegou.

    Tarefas sem recorrência são desativadas após a execução.
    Tarefas recorrentes recebem uma nova data de execução.
    """

    SUPPORTED_REPEATS = {
        "hourly",
        "daily",
        "weekly",
        "monthly",
    }

    def __init__(
        self,
        scheduler: Scheduler,
        executor: Callable[[ScheduledJob], None],
        interval: float = 1.0,
    ) -> None:
        self.scheduler = scheduler
        self.executor = executor
        self.interval = interval

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
        )

    def start(self) -> None:
        if self.running:
            return

        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="SchedulerWorker",
        )

        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=5)

        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.tick()

            self._stop_event.wait(self.interval)

    def tick(self) -> None:
        """
        Executa uma única verificação dos agendamentos.

        Este método também pode ser chamado diretamente
        pelos testes automatizados.
        """

        for job in list(self.scheduler.enabled_jobs):
            now = datetime.now(job.run_at.tzinfo)

            if job.run_at > now:
                continue

            self.executor(job)

            job.last_run = now

            if self._is_recurring(job):
                job.run_at = self._calculate_next_run(
                    job.run_at,
                    job.repeat,
                    now,
                )
            else:
                job.enabled = False

            self.scheduler.save()

    def _is_recurring(
        self,
        job: ScheduledJob,
    ) -> bool:
        if not isinstance(job.repeat, str):
            return False

        return (
            job.repeat.lower().strip()
            in self.SUPPORTED_REPEATS
        )

    def _calculate_next_run(
        self,
        run_at: datetime,
        repeat: str | None,
        now: datetime,
    ) -> datetime:
        normalized_repeat = (
            repeat.lower().strip()
            if isinstance(repeat, str)
            else ""
        )

        next_run = run_at

        while next_run <= now:
            if normalized_repeat == "hourly":
                next_run += timedelta(hours=1)

            elif normalized_repeat == "daily":
                next_run += timedelta(days=1)

            elif normalized_repeat == "weekly":
                next_run += timedelta(weeks=1)

            elif normalized_repeat == "monthly":
                next_run = self._add_one_month(next_run)

            else:
                return run_at

        return next_run

    @staticmethod
    def _add_one_month(
        current: datetime,
    ) -> datetime:
        if current.month == 12:
            year = current.year + 1
            month = 1
        else:
            year = current.year
            month = current.month + 1

        last_day = calendar.monthrange(
            year,
            month,
        )[1]

        day = min(current.day, last_day)

        return current.replace(
            year=year,
            month=month,
            day=day,
        )