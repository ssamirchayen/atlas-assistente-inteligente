from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(slots=True)
class ParsedSchedule:
    command: str
    run_at: datetime
    repeat: str | None = None


class SchedulerParser:
    """
    Extrai informações de agendamento de comandos
    escritos em português.
    """

    _WEEKDAYS = {
        "segunda": 0,
        "segunda-feira": 0,
        "terca": 1,
        "terça": 1,
        "terca-feira": 1,
        "terça-feira": 1,
        "quarta": 2,
        "quarta-feira": 2,
        "quinta": 3,
        "quinta-feira": 3,
        "sexta": 4,
        "sexta-feira": 4,
        "sabado": 5,
        "sábado": 5,
        "domingo": 6,
    }

    def parse(
        self,
        text: str,
        *,
        now: datetime | None = None,
    ) -> ParsedSchedule | None:
        if not text or not text.strip():
            return None

        manaus_timezone = timezone(
            timedelta(hours=-4),
            name="America/Manaus",
        )
        reference = now or datetime.now(manaus_timezone)

        if reference.tzinfo is None:
            reference = reference.replace(
                tzinfo=manaus_timezone,
            )

        normalized = self._remove_atlas_prefix(
            text.strip(),
        )

        parsers = (
            self._parse_every_hour,
            self._parse_daily,
            self._parse_weekly,
            self._parse_relative_minutes,
            self._parse_relative_hours,
            self._parse_tomorrow,
            self._parse_today,
        )

        for parser in parsers:
            result = parser(
                normalized,
                reference,
            )

            if result is not None:
                return result

        return None

    def _parse_every_hour(
        self,
        text: str,
        now: datetime,
    ) -> ParsedSchedule | None:
        match = re.search(
            r"\b(?:a\s+cada\s+hora|de\s+hora\s+em\s+hora)\b",
            text,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        command = self._extract_command(
            text,
            match.start(),
            match.end(),
        )

        if not command:
            return None

        return ParsedSchedule(
            command=command,
            run_at=now + timedelta(hours=1),
            repeat="hourly",
        )

    def _parse_daily(
        self,
        text: str,
        now: datetime,
    ) -> ParsedSchedule | None:
        match = re.search(
            (
                r"\b(?:todo\s+dia|todos\s+os\s+dias)\s+"
                r"(?:à|a|às|as)\s+"
                r"(?P<hour>\d{1,2})"
                r"(?::(?P<minute_colon>\d{2})|"
                r"h(?P<minute_h>\d{2})?)?"
                r"(?:\s*(?P<period>da\s+manh[ãa]|"
                r"da\s+tarde|da\s+noite))?"
                r"\b"
            ),
            text,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        hour, minute = self._read_named_time(match)

        if not self._valid_time(hour, minute):
            return None

        command = self._extract_command(
            text,
            match.start(),
            match.end(),
        )

        if not command:
            return None

        run_at = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if run_at <= now:
            run_at += timedelta(days=1)

        return ParsedSchedule(
            command=command,
            run_at=run_at,
            repeat="daily",
        )

    def _parse_weekly(
        self,
        text: str,
        now: datetime,
    ) -> ParsedSchedule | None:
        match = re.search(
            (
                r"\b(?:toda\s+)?"
                r"(?P<weekday>segunda(?:-feira)?|"
                r"ter[cç]a(?:-feira)?|"
                r"quarta(?:-feira)?|"
                r"quinta(?:-feira)?|"
                r"sexta(?:-feira)?|"
                r"s[áa]bado|domingo)\s+"
                r"(?:à|a|às|as)\s+"
                r"(?P<hour>\d{1,2})"
                r"(?::(?P<minute_colon>\d{2})|"
                r"h(?P<minute_h>\d{2})?)?"
                r"(?:\s*(?P<period>da\s+manh[ãa]|"
                r"da\s+tarde|da\s+noite))?"
                r"\b"
            ),
            text,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        hour, minute = self._read_named_time(match)

        if not self._valid_time(hour, minute):
            return None

        weekday_text = match.group("weekday").lower()
        target_weekday = self._WEEKDAYS.get(weekday_text)

        if target_weekday is None:
            return None

        command = self._extract_command(
            text,
            match.start(),
            match.end(),
        )

        if not command:
            return None

        days_ahead = (target_weekday - now.weekday()) % 7
        run_at = (now + timedelta(days=days_ahead)).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if run_at <= now:
            run_at += timedelta(weeks=1)

        return ParsedSchedule(
            command=command,
            run_at=run_at,
            repeat="weekly",
        )

    def _parse_relative_minutes(
        self,
        text: str,
        now: datetime,
    ) -> ParsedSchedule | None:
        match = re.search(
            r"\bdaqui\s+(?:a\s+)?(\d+)\s+minutos?\b",
            text,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        minutes = int(match.group(1))

        if minutes <= 0:
            return None

        command = self._extract_command(
            text,
            match.start(),
            match.end(),
        )

        if not command:
            return None

        return ParsedSchedule(
            command=command,
            run_at=now + timedelta(minutes=minutes),
        )

    def _parse_relative_hours(
        self,
        text: str,
        now: datetime,
    ) -> ParsedSchedule | None:
        match = re.search(
            r"\bdaqui\s+(?:a\s+)?(\d+)\s+horas?\b",
            text,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        hours = int(match.group(1))

        if hours <= 0:
            return None

        command = self._extract_command(
            text,
            match.start(),
            match.end(),
        )

        if not command:
            return None

        return ParsedSchedule(
            command=command,
            run_at=now + timedelta(hours=hours),
        )

    def _parse_tomorrow(
        self,
        text: str,
        now: datetime,
    ) -> ParsedSchedule | None:
        match = re.search(
            (
                r"\bamanh[ãa]\s+"
                r"(?:à|a|às|as)\s+"
                r"(\d{1,2})"
                r"(?::(\d{2})|h(?:(\d{2}))?)?"
                r"\b"
            ),
            text,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        hour, minute = self._read_time(match)

        if not self._valid_time(hour, minute):
            return None

        command = self._extract_command(
            text,
            match.start(),
            match.end(),
        )

        if not command:
            return None

        run_at = (now + timedelta(days=1)).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        return ParsedSchedule(
            command=command,
            run_at=run_at,
        )

    def _parse_today(
        self,
        text: str,
        now: datetime,
    ) -> ParsedSchedule | None:
        match = re.search(
            (
                r"\bhoje\s+"
                r"(?:à|a|às|as)\s+"
                r"(\d{1,2})"
                r"(?::(\d{2})|h(?:(\d{2}))?)?"
                r"\b"
            ),
            text,
            flags=re.IGNORECASE,
        )

        if match is None:
            return None

        hour, minute = self._read_time(match)

        if not self._valid_time(hour, minute):
            return None

        command = self._extract_command(
            text,
            match.start(),
            match.end(),
        )

        if not command:
            return None

        run_at = now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if run_at <= now:
            return None

        return ParsedSchedule(
            command=command,
            run_at=run_at,
        )

    @classmethod
    def _read_named_time(
        cls,
        match: re.Match[str],
    ) -> tuple[int, int]:
        hour = int(match.group("hour"))
        minute_text = (
            match.group("minute_colon")
            or match.group("minute_h")
            or "0"
        )
        period = match.group("period")

        if period:
            hour = cls._apply_period(hour, period)

        return hour, int(minute_text)

    @staticmethod
    def _apply_period(
        hour: int,
        period: str,
    ) -> int:
        normalized_period = period.lower()

        if "manh" in normalized_period:
            return 0 if hour == 12 else hour

        if "tarde" in normalized_period or "noite" in normalized_period:
            return hour if hour >= 12 else hour + 12

        return hour

    @staticmethod
    def _read_time(
        match: re.Match[str],
    ) -> tuple[int, int]:
        hour = int(match.group(1))
        minute_text = (
            match.group(2)
            or match.group(3)
            or "0"
        )

        return hour, int(minute_text)

    @staticmethod
    def _valid_time(
        hour: int,
        minute: int,
    ) -> bool:
        return 0 <= hour <= 23 and 0 <= minute <= 59

    @staticmethod
    def _remove_atlas_prefix(
        text: str,
    ) -> str:
        return re.sub(
            r"^\s*atlas\s*[,:\-]?\s*",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        ).strip()

    @staticmethod
    def _extract_command(
        text: str,
        start: int,
        end: int,
    ) -> str:
        before = text[:start].strip(" ,.-")
        after = text[end:].strip(" ,.-")

        command = " ".join(
            part
            for part in (before, after)
            if part
        )

        command = re.sub(
            r"^(por\s+favor\s+)?"
            r"(me\s+lembre\s+de|"
            r"me\s+lembre|"
            r"lembre-me\s+de|"
            r"agende|"
            r"programe)\s+",
            "",
            command,
            count=1,
            flags=re.IGNORECASE,
        )

        return re.sub(
            r"\s+",
            " ",
            command,
        ).strip()
