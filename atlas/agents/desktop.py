from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from atlas.agents.base import AgentMetadata
from atlas.core.config import PROJECT_DIR
from atlas.planner.actions import Action


class DesktopAgent:
    metadata = AgentMetadata(
        name="desktop",
        display_name="Desktop Agent",
        description="Planeja abertura de programas e ações do ambiente local.",
        domains=("desktop", "windows", "applications"),
        priority=100,
    )

    def __init__(
        self,
        project_path: Path | str | None = None,
    ) -> None:
        self.project_path = Path(
            project_path or PROJECT_DIR
        ).expanduser().resolve()
        self.programs: dict[str, list[str]] = {
            "bloco de notas": ["notepad.exe"],
            "notepad": ["notepad.exe"],

            "calculadora": ["calc.exe"],
            "calc": ["calc.exe"],

            "paint": ["mspaint.exe"],

            "explorador": ["explorer.exe"],
            "explorador de arquivos": ["explorer.exe"],

            "powershell": ["powershell.exe"],
            "terminal": ["powershell.exe"],

            "prompt de comando": ["cmd.exe"],
            "cmd": ["cmd.exe"],

            "vs code": ["code"],
            "vscode": ["code"],
            "visual studio code": ["code"],
        }

    def plan(self, command: str) -> list[Action]:
        normalized = self._normalize(command)

        project_plan = self._project_plan(normalized)

        if project_plan:
            return project_plan

        program_plan = self._program_plan(normalized)

        if program_plan:
            return program_plan

        return []

    def _project_plan(
        self,
        command: str,
    ) -> list[Action]:
        project_phrases = (
            "continue nosso projeto",
            "continuar nosso projeto",
            "continue o projeto",
            "continuar o projeto",
            "abra nosso projeto",
            "abra o projeto atlas",
            "abrir o projeto atlas",
            "vamos continuar o atlas",
            "vamos programar",
        )

        is_project_command = any(
            phrase in command
            for phrase in project_phrases
        )

        wants_vscode_project = (
            self._mentions_vscode(command)
            and (
                "atlas" in command
                or "projeto" in command
                or "pasta" in command
            )
        )

        if not is_project_command and not wants_vscode_project:
            return []

        arguments = [
            "code",
            str(self.project_path),
        ]

        if any(
            term in command
            for term in (
                "main",
                "main py",
                "arquivo principal",
            )
        ):
            arguments.append(
                str(self.project_path / "main.py")
            )

        return [
            Action(
                type="process.start",
                parameters={
                    "command": arguments,
                },
            )
        ]

    def _program_plan(
        self,
        command: str,
    ) -> list[Action]:
        open_match = re.match(
            (
                r"^(?:abra|abre|abrir|inicie|iniciar)"
                r"(?: o| a)?\s+(.+)$"
            ),
            command,
        )

        if not open_match:
            return []

        requested_program = open_match.group(1).strip()

        for name, executable in self.programs.items():
            if (
                requested_program == name
                or name in requested_program
            ):
                return [
                    Action(
                        type="process.start",
                        parameters={
                            "command": executable,
                        },
                    )
                ]

        return []

    @staticmethod
    def _mentions_vscode(command: str) -> bool:
        return any(
            term in command
            for term in (
                "vscode",
                "vs code",
                "visual studio code",
                "visual studio",
            )
        )

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().strip()

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(character)
        )

        text = re.sub(
            r"[^\w\s]",
            " ",
            text,
        )

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()
