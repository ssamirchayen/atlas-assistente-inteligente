from datetime import UTC, datetime, timedelta

from atlas.scheduler.parser import (
    ParsedSchedule,
    SchedulerParser,
)

REFERENCE_TIME = datetime(
    2026,
    7,
    25,
    10,
    0,
    tzinfo=UTC,
)


def test_parse_invalid_text() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        "abra o navegador",
        now=REFERENCE_TIME,
    )

    assert result is None


def test_parse_relative_minutes() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        "Atlas, daqui 30 minutos abra o VS Code",
        now=REFERENCE_TIME,
    )

    assert isinstance(
        result,
        ParsedSchedule,
    )

    assert result.command == "abra o VS Code"

    assert result.run_at == (
        REFERENCE_TIME
        + timedelta(minutes=30)
    )

    assert result.repeat is None


def test_parse_relative_hours() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        "daqui 2 horas abra o navegador",
        now=REFERENCE_TIME,
    )

    assert result is not None
    assert result.command == "abra o navegador"

    assert result.run_at == (
        REFERENCE_TIME
        + timedelta(hours=2)
    )


def test_parse_tomorrow() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        (
            "Atlas, me lembre amanhã às 08:30 "
            "de abrir o CRM"
        ),
        now=REFERENCE_TIME,
    )

    assert result is not None
    assert result.command == "abrir o CRM"

    assert result.run_at == datetime(
        2026,
        7,
        26,
        8,
        30,
        tzinfo=UTC,
    )


def test_parse_tomorrow_with_h_format() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        "amanhã às 9h abrir o sistema",
        now=REFERENCE_TIME,
    )

    assert result is not None
    assert result.command == "abrir o sistema"
    assert result.run_at.hour == 9
    assert result.run_at.minute == 0


def test_parse_today() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        "hoje às 14h abra o bloco de notas",
        now=REFERENCE_TIME,
    )

    assert result is not None

    assert result.command == (
        "abra o bloco de notas"
    )

    assert result.run_at == datetime(
        2026,
        7,
        25,
        14,
        0,
        tzinfo=UTC,
    )


def test_reject_past_time_today() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        "hoje às 8h abra o navegador",
        now=REFERENCE_TIME,
    )

    assert result is None


def test_reject_invalid_hour() -> None:
    parser = SchedulerParser()

    result = parser.parse(
        "amanhã às 29h abra o navegador",
        now=REFERENCE_TIME,
    )

    assert result is None