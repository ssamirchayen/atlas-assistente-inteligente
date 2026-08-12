from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from atlas.scheduler.job import ScheduledJob
from atlas.scheduler.scheduler import Scheduler
from atlas.scheduler.worker import SchedulerWorker


def create_scheduler(
    tmp_path: Path,
) -> Scheduler:
    return Scheduler(
        storage_path=tmp_path / "scheduler.json"
    )


def test_tick_executes_due_job(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)
    executed_jobs: list[ScheduledJob] = []

    job = ScheduledJob(
        title="Abrir navegador",
        command="abrir navegador",
        run_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=executed_jobs.append,
    )

    worker.tick()

    assert executed_jobs == [job]
    assert job.enabled is False
    assert job.last_run is not None


def test_tick_does_not_execute_future_job(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)
    executed_jobs: list[ScheduledJob] = []

    job = ScheduledJob(
        title="Abrir navegador",
        command="abrir navegador",
        run_at=datetime.now(UTC) + timedelta(hours=1),
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=executed_jobs.append,
    )

    worker.tick()

    assert executed_jobs == []
    assert job.enabled is True
    assert job.last_run is None


def test_tick_does_not_execute_disabled_job(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)
    executed_jobs: list[ScheduledJob] = []

    job = ScheduledJob(
        title="Abrir navegador",
        command="abrir navegador",
        run_at=datetime.now(UTC) - timedelta(seconds=1),
        enabled=False,
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=executed_jobs.append,
    )

    worker.tick()

    assert executed_jobs == []
    assert job.enabled is False
    assert job.last_run is None


def test_worker_start_and_stop(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda job: None,
        interval=0.01,
    )

    assert worker.running is False

    worker.start()

    assert worker.running is True

    worker.stop()

    assert worker.running is False


def test_executed_job_is_persisted(
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "scheduler.json"

    scheduler = Scheduler(
        storage_path=storage_path
    )

    job = ScheduledJob(
        title="Abrir navegador",
        command="abrir navegador",
        run_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda scheduled_job: None,
    )

    worker.tick()

    reloaded_scheduler = Scheduler(
        storage_path=storage_path
    )

    reloaded_job = reloaded_scheduler.get_job(job.id)

    assert reloaded_job is not None
    assert reloaded_job.enabled is False
    assert reloaded_job.last_run is not None


def test_hourly_job_is_rescheduled(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)

    original_run_at = (
        datetime.now(UTC) - timedelta(minutes=5)
    )

    job = ScheduledJob(
        title="Sincronizar arquivos",
        command="sincronizar arquivos",
        run_at=original_run_at,
        repeat="hourly",
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda scheduled_job: None,
    )

    worker.tick()

    assert job.enabled is True
    assert job.last_run is not None
    assert job.run_at > datetime.now(UTC)
    assert job.run_at == original_run_at + timedelta(hours=1)


def test_daily_job_is_rescheduled(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)

    original_run_at = (
        datetime.now(UTC) - timedelta(hours=1)
    )

    job = ScheduledJob(
        title="Abrir CRM",
        command="abrir crm",
        run_at=original_run_at,
        repeat="daily",
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda scheduled_job: None,
    )

    worker.tick()

    assert job.enabled is True
    assert job.run_at == original_run_at + timedelta(days=1)


def test_weekly_job_is_rescheduled(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)

    original_run_at = (
        datetime.now(UTC) - timedelta(days=1)
    )

    job = ScheduledJob(
        title="Gerar relatório",
        command="gerar relatório",
        run_at=original_run_at,
        repeat="weekly",
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda scheduled_job: None,
    )

    worker.tick()

    assert job.enabled is True
    assert job.run_at == original_run_at + timedelta(weeks=1)


def test_monthly_job_is_rescheduled(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)

    job = ScheduledJob(
        title="Fechamento mensal",
        command="gerar fechamento mensal",
        run_at=datetime(
            2026,
            1,
            31,
            10,
            0,
            tzinfo=UTC,
        ),
        repeat="monthly",
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda scheduled_job: None,
    )

    next_run = worker._calculate_next_run(
        job.run_at,
        job.repeat,
        datetime(
            2026,
            2,
            1,
            10,
            0,
            tzinfo=UTC,
        ),
    )

    assert next_run == datetime(
        2026,
        2,
        28,
        10,
        0,
        tzinfo=UTC,
    )


def test_recurring_job_skips_missed_occurrences(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)

    original_run_at = (
        datetime.now(UTC) - timedelta(days=3)
    )

    job = ScheduledJob(
        title="Abrir CRM",
        command="abrir crm",
        run_at=original_run_at,
        repeat="daily",
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda scheduled_job: None,
    )

    worker.tick()

    assert job.enabled is True
    assert job.run_at > datetime.now(UTC)


def test_unknown_repeat_disables_job(
    tmp_path: Path,
) -> None:
    scheduler = create_scheduler(tmp_path)

    job = ScheduledJob(
        title="Comando desconhecido",
        command="executar comando",
        run_at=datetime.now(UTC) - timedelta(seconds=1),
        repeat="sometimes",
    )

    scheduler.add_job(job)

    worker = SchedulerWorker(
        scheduler=scheduler,
        executor=lambda scheduled_job: None,
    )

    worker.tick()

    assert job.enabled is False