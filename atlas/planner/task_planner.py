from __future__ import annotations

import re


class TaskPlanner:
    """
    Divide um comando complexo em várias tarefas menores.
    """

    def __init__(self) -> None:
        self._split_pattern = re.compile(
            r"\s*(?:,| e depois | depois | então | entao | e |;)\s*",
            flags=re.IGNORECASE,
        )

    def split(self, command: str) -> list[str]:
        """
        Divide um comando em várias etapas.

        Exemplo:

        "Abra o Chrome e pesquise Python depois maximize a janela"

        retorna:

        [
            "Abra o Chrome",
            "pesquise Python",
            "maximize a janela"
        ]
        """

        command = command.strip()

        if not command:
            return []

        parts = self._split_pattern.split(command)

        tasks = []

        for part in parts:
            part = part.strip()

            if not part:
                continue

            tasks.append(part)

        return tasks