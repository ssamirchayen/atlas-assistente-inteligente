from datetime import UTC, datetime

from atlas.scheduler import ScheduledJob, Scheduler


def test_scheduler_saves_and_loads_jobs(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "scheduler.json"
    )

    scheduler = Scheduler(database_path)

    job = ScheduledJob(
        title="Abrir CRM",
        command="abrir crm",
        run_at=datetime(
            2026,
            7,
            25,
            8,
            0,
            tzinfo=UTC,
        ),
        repeat="daily",
    )

    scheduler.add_job(job)

    assert scheduler.total == 1
    assert database_path.exists()

    restored_scheduler = Scheduler(
        database_path
    )

    restored_job = restored_scheduler.get_job(
        job.id
    )

    assert restored_scheduler.total == 1
    assert restored_job is not None
    assert restored_job.title == "Abrir CRM"
    assert restored_job.command == "abrir crm"
    assert restored_job.repeat == "daily"
    assert restored_job.run_at == job.run_at


def test_scheduler_removes_job(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "scheduler.json"
    )

    scheduler = Scheduler(database_path)

    job = scheduler.add_job(
        ScheduledJob(
            title="Teste",
            command="executar teste",
        )
    )

    removed = scheduler.remove_job(
        job.id
    )

    assert removed is True
    assert scheduler.total == 0

    restored_scheduler = Scheduler(
        database_path
    )

    assert restored_scheduler.total == 0


def test_remove_unknown_job_returns_false(
    tmp_path,
) -> None:
    scheduler = Scheduler(
        tmp_path / "scheduler.json"
    )

    removed = scheduler.remove_job(
        "id-inexistente"
    )

    assert removed is False


def test_corrupted_database_is_ignored(
    tmp_path,
) -> None:
    database_path = (
        tmp_path
        / "scheduler.json"
    )

    database_path.write_text(
        "arquivo inválido",
        encoding="utf-8",
    )

    scheduler = Scheduler(database_path)

    assert scheduler.total == 0